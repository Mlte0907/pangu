"""**纠正优先于去重**（2026-09-30 新增语义）。

要守住的规则
------------
写入一条新记忆时，`ingestion._dedup_and_fuse` 有三种结局：

| 结局 | 条件 | 后果 |
|---|---|---|
| **拒绝写入** | 与旧记忆「说的是同一件事」 | 旧的不动，新的丢掉 |
| **建立 supersede** | 同主题、且新内容明显更丰富 | 新的写入，旧的标为已替代 |
| **交给冲突检测** | 同主题、又不是真重复 | 新的写入，由 `_detect_conflicts` 判定 |

**「拒绝写入」是三者里唯一会丢信息的**。旧实现把 `SUPERSEDE_THRESHOLD`(0.65，
用来圈「同主题」)顺手当成了拒绝门槛，于是**等长的纠正被判成重复、静默丢弃** ——
错的那条永远留在库里。按盘古的记忆模型（纠错优先、旧记忆标 superseded 且可追溯），
这是最坏的结果。

⚠ **相似度单独分不开「重述」和「纠正」**：文本够长、共享大部分字符时，
只翻转极性那几个字，向量几乎不动。实测
「测试缓存查询 X: 配置正确」vs「…配置是错误的」cos=**0.9324**，
比「真重复·加同义前缀」（0.9582）只低一点点，离 0.92 的拒绝门槛只差 0.012。
⇒ 拒绝写入必须叠一道**极性否决**（`conflict.polarity_escalation`）。

这些测试用 **stub 嵌入服务**（自己指定向量 ⇒ 相似度精确可控），
**不加载真实模型**，离线可跑、毫秒级。
"""

from __future__ import annotations

import math

import pytest

from pangu.core.palace import Drawer
from pangu.memory import ingestion as ing_mod
from pangu.memory.conflict import polarity_escalation, text_polarity

WING = "tech"
ROOM = "general"


class _StubEmbedSvc:
    """把文本映射到指定向量，从而**精确控制**余弦相似度。"""

    def __init__(self, mapping: dict[str, list[float]]):
        self._m = mapping

    def embed(self, text: str) -> list[float]:
        return self._m.get(text, [0.0] * 384)


def _unit(angle_deg: float) -> list[float]:
    """造一个 384 维单位向量，与参考轴夹角恰为 angle_deg（欧氏空间里余弦=cos角）。"""
    rad = math.radians(angle_deg)
    v = [0.0] * 384
    v[0] = math.cos(rad)
    v[1] = math.sin(rad)
    return v


def _drawer(did: str, content: str, vec: list[float]) -> Drawer:
    return Drawer(
        id=did,
        content=content,
        wing=WING,
        room=ROOM,
        tags=[],
        created_at="2026-01-01T00:00:00",
        metadata={"embedding": vec},
    )


@pytest.fixture
def stub_embedder(monkeypatch):
    """装一个可配置的 stub：`stub(text1, text2, cos=0.95)`。"""

    def _install(cos: float, old_text: str, new_text: str):
        # 以 old 的向量为参考轴，让 new 与它的余弦恰为 cos
        base = _unit(0.0)
        target = _unit(math.degrees(math.acos(max(-1.0, min(1.0, cos)))))
        mapping = {old_text: base, new_text: target}
        monkeypatch.setattr(ing_mod, "get_embedding_service", lambda: _StubEmbedSvc(mapping))
        return mapping

    return _install


# ── 1. 极性判定本身（不需要模型） ──────────────────────────────


class TestPolarityEscalation:
    def test_same_text_is_not_escalation(self):
        t = "今天开会讨论了数据库备份策略"
        assert text_polarity(t) == (False, False)
        assert polarity_escalation(t, t) is False

    def test_correction_adds_negative_word(self):
        old = "API 配置: token 是正确，应该启用。"
        new = "API 配置: token 是错误的，必须禁用。"
        assert polarity_escalation(old, new) is True

    def test_correction_drops_positive_word(self):
        assert polarity_escalation("缓存策略是安全的", "缓存策略不安全") is True

    def test_plain_addition_without_polarity_is_not_escalation(self):
        """只是补充细节、没有极性变化 ⇒ 不是纠正（否则会把所有扩写都当成纠正）。"""
        old = "数据库备份策略说明"
        new = "数据库备份策略说明：每日 03:00 全量，周日增量"
        assert polarity_escalation(old, new) is False

    def test_both_sides_polarity_does_not_fool_it(self):
        """长句常常正负词都有 —— 判据必须是**增量**，不是「是否同时含正负词」。

        「配置是错误的」里「是」是正词、「错误」是负词，两边都命中；
        要求「干净翻转」的话这种句子永远判不出来（第一版就是这么失败的）。
        """
        pos, neg = text_polarity("API 配置: token 是错误的，必须禁用。")
        assert pos and neg, "这句本来就正负都有 —— 正是干净翻转判据失效的原因"
        assert polarity_escalation("API 配置: token 是正确，应该启用。", "API 配置: token 是错误的，必须禁用。") is True


# ── 2. 去重三结局 ──────────────────────────────────────────────


class TestDedupCorrectionFirst:
    def test_exact_duplicate_is_rejected(self, stub_embedder):
        t = "今天开会讨论了数据库备份策略，需要在下周之前落地"
        stub_embedder(1.0, t, t)
        old = _drawer("a" * 32, t, _unit(0.0))
        dup, fused, sup = ing_mod._dedup_and_fuse(t, WING, ROOM, [old])
        assert dup is not None and fused is None and sup is None

    def test_near_duplicate_same_polarity_is_rejected(self, stub_embedder):
        """相似度 0.97（远超 0.92 门槛）且**无极性变化** ⇒ 认定真重复，拒绝写入。"""
        old_t = "今天开会讨论了数据库备份策略，需要在下周之前落地"
        new_t = "今天开会讨论了数据库备份策略，需要在下周之前落地。"  # 只多一个句号
        stub_embedder(0.97, old_t, new_t)
        old = _drawer("a" * 32, old_t, _unit(0.0))
        dup, fused, sup = ing_mod._dedup_and_fuse(new_t, WING, ROOM, [old])
        assert dup is not None, "无极性变化的高相似对必须仍被拒（否则去重形同虚设）"
        assert sup is None

    def test_high_similarity_correction_is_NOT_rejected(self, stub_embedder):
        """★ 本次修复的核心：相似度 0.95（**高于** 0.92 门槛）但极性翻转 ⇒
        这是纠正，**必须放行**，不能当重复丢掉。

        这是实测里最难的一类：`测试缓存查询 X: 配置正确` vs `…配置是错误的`
        cos=0.9324，靠相似度根本分不出来。
        """
        old_t = "测试缓存查询 abc: 配置正确"
        new_t = "测试缓存查询 abc: 配置是错误的"
        stub_embedder(0.95, old_t, new_t)
        old = _drawer("a" * 32, old_t, _unit(0.0))
        dup, fused, sup = ing_mod._dedup_and_fuse(new_t, WING, ROOM, [old])
        assert dup is None, "极性翻转的对被判成重复 ⇒ 纠正被静默丢弃（本次修的 bug）"
        assert sup is None, "它不够'丰富'，不该由 dedup 直接建 supersede，应交给 _detect_conflicts"

    def test_similar_but_not_richer_is_written_not_rejected(self, stub_embedder):
        """同主题、不是真重复、又不够丰富 ⇒ **放行写入**，交给冲突检测。

        这是有意放宽的：旧实现在这里直接拒绝。宁可多写一条让冲突检测判，
        也不要静默丢掉一条可能很重要的记忆。
        """
        old_t = "数据库备份策略：每日 03:00 全量"
        new_t = "数据库备份：每天凌晨三点全量"  # 同义重述，相似但不极性变化
        stub_embedder(0.75, old_t, new_t)
        old = _drawer("a" * 32, old_t, _unit(0.0))
        dup, fused, sup = ing_mod._dedup_and_fuse(new_t, WING, ROOM, [old])
        assert dup is None, "0.75 < 0.92，本来就不该按真重复拒；也不该在这里被丢"

    def test_richer_content_still_establishes_supersede(self, stub_embedder):
        """明显更丰富 ⇒ 仍由 dedup 直接给出 supersede_id（不需要 LLM 的那条路）。

        这条路是**降级兜底**：LLM 不可用时，"新内容更丰富"仍能建立替代关系。
        回归守护：别把这条也一起改没了。
        """
        old_t = "token 应该是启用的"
        new_t = "token 应该是启用的，实测 401 证明启用会失败；正确做法是禁用，并同步轮换密钥、检查调用方超时配置、补充回滚预案与灰度开关，另外要把这次事故的时间线、影响面和回滚步骤写进复盘文档，下周一之前完成全部整改并同步给相关方"
        stub_embedder(0.70, old_t, new_t)
        old = _drawer("a" * 32, old_t, _unit(0.0))
        dup, fused, sup = ing_mod._dedup_and_fuse(new_t, WING, ROOM, [old])
        assert dup is None
        assert sup == old.id, "明显更丰富时必须仍给出 supersede_id"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
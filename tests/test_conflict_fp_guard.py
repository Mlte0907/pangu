"""冲突检测假阳性守卫（2026-09-27）。

起因：用户写入新记忆时，服务端自动把一条**毫无关系**的旧记忆标为
`superseded`、移出常规搜索（用户不知情）。上云实测复现，根因是关键词路的
三处**子串假阳性**：

    「于是 gAAAAAB… 直出」   vs 「容易误以为当前目录**不是** git」
    「**有**意 fail-open」     vs 「声明块 210-217 **没有** llmDaily」
    「455 **pass**ed」        vs 「React fiber 的 dash.stats.**error**」

三条凑出 confidence=0.8 → ≥ min_confidence(0.3) → 判为冲突。

而**语义相似度实测只有 0.4724，低于向量路自己的 0.5 阈值** —— 也就是说系统
其实知道这两条不像，是关键词路**压根不看相似度**（`_keyword_conflict_detect`
调 `_contradiction_score` 时不传 `semantic_sim`，默认 0.0），才绕过了这道闸。

本文件锁三件事：
  1. **相似度不够就不许判冲突** —— 语义不像的两条不可能是同一事实的矛盾；
  2. 子串巧合不得单独构成冲突（最长匹配：「不是」覆盖「是」、「passed」覆盖「pass」）；
  3. 真冲突（高相似 + 干净矛盾表述）仍必须判得出来 —— 别为了防误杀把功能关死。

风险背景：误判的后果是**旧记忆静默退出搜索**，代价远高于漏判（多留一条重复）。
因此本文件的守卫方向刻意偏保守：宁可漏判，不可误杀。
"""

from __future__ import annotations

import math

import pytest

from pangu.core.palace import Drawer
from pangu.memory.conflict import ConflictDetector


class _FakeEmbedder:
    """可控相似度的假 embedder。

    用单位向量的夹角精确表达相似度：`cos(theta)` 即目标 sim。
    生产走 ONNX，测试不必拉起模型 —— 本文件考的是**判定逻辑**，不是向量质量。
    """

    def __init__(self, similarities: dict[frozenset[str], float] | None = None, default: float = 0.0):
        self._pair_sim = similarities or {}
        self._default = default
        self._texts: dict[str, int] = {}

    @staticmethod
    def _key(a: str, b: str) -> frozenset[str]:
        return frozenset((a, b))

    def embed(self, text: str):
        raise NotImplementedError("本测试只走 embed_batch")

    def embed_batch(self, texts: list[str]):
        # 两两夹角无法用独立向量同时表达任意矩阵，这里按「第一对」构造：
        # texts[0] 固定在 0°，texts[1] 放在 acos(sim) 处，其余退化到 0°。
        if len(texts) >= 2:
            sim = self._pair_sim.get(self._key(texts[0], texts[1]), self._default)
            sim = max(-1.0, min(1.0, sim))
            theta = math.acos(sim)
            return [[1.0, 0.0], [math.cos(theta), math.sin(theta)]] + [
                [1.0, 0.0] for _ in texts[2:]
            ]
        return [[1.0, 0.0] for _ in texts]


def _detector(sim: float | None) -> ConflictDetector:
    """构造 detector；sim=None 表示「没有 embedder」的降级场景。"""
    d = ConflictDetector()
    d._embedder = None if sim is None else _FakeEmbedder(default=sim)
    return d


# ── 2026-09-27 真实事故的代表性片段（截取自两条记忆的实际内容）──

NEW_SIDE = """加密读侧 fail-open + 启动自检采样面修复（2026-09-27，commit b45b265，已部署云端）
一、修了什么
1) **读侧静默吐密文**：pangu/memory/encryption.py 的 decrypt() 在 _get_fernet()
返回 None（cryptography 缺失 / 密钥非法 / 密钥为空）时直接 return ciphertext。
这与它自己 docstring 宣称的「不再静默返回密文」矛盾 —— 2026-09-19 修过同款坑，
但只修了「密钥不匹配」那一态，**漏了「加密根本不可用」这一态**。于是 gAAAAAB…
直出到搜索结果、召回注入与仪表盘。而**写侧 encrypt 是有意 fail-open**（原样存
明文 + 打 WARNING）。测试实现前 6 红 8 绿、实现后 15 绿。受影响面 455 passed，
全量 1968 passed，启动体检报 ERROR 若干。
"""

OLD_SIDE = """pangu-dev/AGENTS.md 更新 + dsh-pangu 仪表盘「不显示」根因定位（2026-09-27）
一、AGENTS.md 改进：环境速查拆成「本地 = git 仓库 / 云端非 git scp 部署」两行 ——
原文只写云端非 git，容易让 agent 误以为当前目录**不是** git。
新增「dsh-pangu 仪表盘（跨仓）」3 条：真错误要看 React fiber 上的
dash.stats.**error** 与 web.log。fetchPanguStats 的声明块（210-217）**没有**
llmDaily/llmTotal；256-257 却赋值 → 静默吞错。
"""


class TestNoConflictWhenSemanticallyUnrelated:
    """① 相似度不够 ⇒ 不许判冲突。

    这是本次事故的决定性闸门：实测 sim=0.4724 < 0.5，向量路被挡，
    关键词路却因不看相似度而放行。
    """

    def test_real_incident_pair_is_not_a_conflict(self):
        d = _detector(sim=0.4724)  # 上云实测值
        conflicts = d.detect_conflicts(
            [Drawer(id="new", content=NEW_SIDE), Drawer(id="old", content=OLD_SIDE)]
        )
        assert conflicts == [], (
            f"语义相似度 0.4724 低于 0.5 阈值的两条记忆被判成冲突："
            f"{[(c.confidence, c.description) for c in conflicts]}"
        )

    @pytest.mark.parametrize("sim", [0.0, 0.1, 0.3, 0.4724, 0.49])
    def test_keyword_path_respects_similarity_threshold(self, sim):
        """关键词路必须与向量路用同一把相似度尺子。"""
        d = _detector(sim=sim)
        conflicts = d.detect_conflicts(
            [Drawer(id="a", content=NEW_SIDE), Drawer(id="b", content=OLD_SIDE)]
        )
        assert conflicts == [], f"sim={sim} 仍被判冲突: {[(c.confidence, c.description) for c in conflicts]}"

    def test_substring_coincidence_alone_is_not_enough(self):
        """单靠子串巧合（「于是」撞「不是」）不得构成冲突。"""
        d = _detector(sim=0.4724)
        # 只要语义不像，哪怕满篇反义词也不许判
        a = Drawer(id="a", content="状态正确 成功 完成 支持 启用 有 配置 version 结果")
        b = Drawer(id="b", content="状态错误 失败 中断 不支持 禁用 没有 配置 version 结果")
        assert d.detect_conflicts([a, b]) == []


class TestRealConflictStillDetected:
    """② 防误杀不能把功能关死 —— 真冲突仍必须判得出来。"""

    def test_high_similarity_with_clean_contradiction(self):
        d = _detector(sim=0.92)
        a = Drawer(id="a", content="盘古 REST 服务端口配置为 19529，状态正确，部署结论已确认")
        b = Drawer(id="b", content="盘古 REST 服务端口配置为 8080，状态错误，部署结论需更正")
        conflicts = d.detect_conflicts([a, b])
        assert conflicts, "高相似度 + 干净矛盾表述必须判出冲突（否则功能等于被关掉）"
        assert conflicts[0].confidence >= 0.3, conflicts[0].confidence

    def test_emergency_pair_without_embedder_does_not_crash(self):
        """没有 embedder 时（降级）不许抛异常。"""
        d = _detector(sim=None)
        a = Drawer(id="a", content="端口 19529，状态正确，配置 结果 决定")
        b = Drawer(id="b", content="端口 8080，状态错误，配置 结果 决定")
        d.detect_conflicts([a, b])  # 不抛即通过


class TestMatchIsLongestNotSubstring:
    """③ 最长匹配：「不是」须覆盖其内部的「是」，「passed」须覆盖「pass」。"""

    @pytest.mark.parametrize(
        "text,expect_pos,expect_neg,why",
        [
            # 注意：样本里不能混入词表自身的词（如「容易」是正词），否则断言自相矛盾
            ("当前目录不是 git", False, True, "「不是」不应拆出正词「是」"),
            ("于是 gAAAAAB 直出到搜索结果", True, False, "「于是」里的「是」是独立正词"),
            ("实现后 455 passed 全量通过", True, False, "passed 含 pass，算正词"),
            ("React fiber 的 dash.stats.error", False, True, "error 是负词"),
            ("声明块 210-217 没有 llmDaily", False, True, "「没有」不应拆出正词「有」"),
            ("该方案支持启用，210-217 有字段", True, False, "正常正词要照常命中"),
        ],
    )
    def test_longest_match_wins(self, text, expect_pos, expect_neg, why):
        d = _detector(sim=0.9)
        pos, neg = d._polarity(text)
        assert pos is expect_pos, f"{why}：pos={pos}"
        assert neg is expect_neg, f"{why}：neg={neg}"

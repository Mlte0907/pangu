"""`MemoryEvolution.find_related_memories` 的两道关卡（2026-09-28 修复）。

背景：机制早就写好了，但**云端快照表 `memory_snapshots.json` 是 0 条** ——
即 `should_replace` → `save_snapshot` 这条链**从未触发过**。根因是两道关卡：

1. **密文**：`content` 在创建 drawer 时就被加密（`ingestion._encrypt_text`），
   而本函数直接拿 `to_dict()["content"].lower()` 比对 ⇒ 关键词重叠恒 0。
2. **中文按空格切**：`str.split()` 对中文把**整句当一个词** ⇒ 除非两句完全相同，
   `word_overlap` 恒 0 —— 就算修了解密，这道仍在。

两道都修，机制才真的转起来。**这是「把现有机制用起来」而不是新增机制。**
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from pangu.memory.evolution import MemoryEvolution, _plain_text, _tokenize


def _ev() -> MemoryEvolution:
    return MemoryEvolution()


class TestPlainText:
    """① 解密：密文要能解开，解不开当空串（宁可不替换，也不拿乱码比对）。"""

    def test_plaintext_passes_through(self, monkeypatch):
        assert _plain_text("盘古服务端口 19529") == "盘古服务端口 19529"

    def test_ciphertext_is_decrypted(self, monkeypatch):
        from pangu.memory import encryption as enc

        monkeypatch.setattr(enc, "_fernet", None)
        monkeypatch.setattr(enc, "_enabled", False)
        monkeypatch.setenv("PANGU_ENCRYPTION_KEY", Fernet.generate_key().decode())

        ct = enc.encrypt("盘古部署方式是 scp 覆盖")
        assert ct.startswith("gAAAAA")
        assert _plain_text(ct) == "盘古部署方式是 scp 覆盖"

    def test_undecryptable_ciphertext_returns_empty(self, monkeypatch):
        """解不开 ⇒ 空串。绝不能把 gAAAAA… 丢去比对。"""
        out = _plain_text("gAAAAAbm90LWEtcmVhbC1rZXk")
        assert out == "" or "gAAAAA" not in out, out

    def test_empty_and_non_str_safe(self):
        assert _plain_text("") == ""
        assert _plain_text(None) == ""
        assert _plain_text(12345) == ""


class TestTokenize:
    """② 分词：中文不能用 split。"""

    def test_chinese_is_segmented_not_one_chunk(self):
        """split 会把整句当一个词 —— 分词后必须是多个词。"""
        text = "盘古服务端口配置为 19529"
        assert len(_tokenize(text)) > 1, f"分词结果过于粗糙: {_tokenize(text)}"

    def test_split_would_have_failed(self):
        """反证：原实现的 split 对**无空格的纯中文**只切出 1 个词。

        （样本必须不含空格 —— 中英混排里的空格会让 split 也能切开，
        那就测不出「中文必须分词」这个点了。）
        """
        text = "盘古服务端口配置为部署方式确认"
        assert len(set(text.split())) == 1, f"前提变了: {set(text.split())}"
        assert len(_tokenize(text)) > 1, "jieba 应把它切成多个词"

    def test_english_splits_on_whitespace(self):
        toks = _tokenize("deploy from main only")
        assert {"deploy", "from", "main"} <= toks

    def test_punctuation_dropped(self):
        toks = _tokenize("端口是 19529，状态正确")
        assert "，" not in toks and "," not in toks

    def test_empty_returns_empty(self):
        assert _tokenize("") == set()
        assert _tokenize("   ") == set()


class TestFindRelated:
    """③ 端到端：两道关卡都修好后，相关记忆必须找得到。"""

    def test_encrypted_related_memories_are_found(self, monkeypatch):
        """★ 密文 content 也必须能配对 —— 修复前恒返回空，快照 0 条。"""
        from pangu.memory import encryption as enc

        monkeypatch.setattr(enc, "_fernet", None)
        monkeypatch.setattr(enc, "_enabled", False)
        monkeypatch.setenv("PANGU_ENCRYPTION_KEY", Fernet.generate_key().decode())

        new = {"id": "n1", "content": enc.encrypt("盘古 REST 服务端口配置为 19529"), "tags": []}
        old = {"id": "o1", "content": enc.encrypt("盘古 REST 服务端口配置为 19529"), "tags": []}

        got = _ev().find_related_memories(new, [old])
        assert got, "两条相同内容的密文记忆应被判为相关（修复前恒为空）"
        assert got[0]["id"] == "o1"

    def test_chinese_paraphrase_is_found(self):
        """中文改写也要能找到 —— split 对中文整句当一词，靠分词才有重叠。

        注意样本要真有足够重叠（word_overlap*0.6 ≥ 0.3 ⇒ 重叠率需 >0.5），
        否则是测「相似度阈值」而不是测「分词是否生效」。
        """
        new = {"id": "n1", "content": "盘古 REST 服务端口配置为 19529，部署方式是 scp 覆盖", "tags": []}
        old = {"id": "o1", "content": "盘古 REST 服务端口配置为 19529，部署走 scp 覆盖", "tags": []}

        got = _ev().find_related_memories(new, [old])
        assert got, "中文改写应靠分词找到，不能靠整句相等"

    def test_genuinely_different_text_still_below_threshold(self):
        """只有一两个词重叠的不该达标 —— 分词变细不能换来乱匹配。"""
        new = {"id": "n1", "content": "盘古 REST 服务端口配置为 19529，部署方式是 scp 覆盖", "tags": []}
        old = {"id": "o1", "content": "今天午饭吃了番茄鸡蛋面，天气不错出门散步", "tags": []}
        assert _ev().find_related_memories(new, [old]) == []

    def test_unrelated_is_not_matched(self):
        """无关的不许硬凑 —— 否则会触发不该发生的替换。"""
        new = {"id": "n1", "content": "盘古 REST 服务端口配置为 19529", "tags": []}
        old = {"id": "o1", "content": "今天午饭吃了番茄鸡蛋面天气不错", "tags": []}

        assert _ev().find_related_memories(new, [old]) == []

    def test_self_is_skipped(self):
        m = {"id": "n1", "content": "盘古服务端口 19529", "tags": []}
        assert _ev().find_related_memories(m, [m]) == []

    def test_tag_overlap_alone_can_match(self):
        new = {"id": "n1", "content": "完全不同的新内容", "tags": ["盘古", "部署"]}
        old = {"id": "o1", "content": "另一段新内容", "tags": ["盘古", "部署"]}
        got = _ev().find_related_memories(new, [old])
        assert got, "标签重叠(0.4×2)应能单独达标"

    def test_limit_five(self):
        """最多返回 5 个 —— 防止相关列表无界膨胀。"""
        new = {"id": "n1", "content": "盘古 REST 服务端口配置为 19529", "tags": []}
        olds = [{"id": f"o{i}", "content": "盘古 REST 服务端口配置为 19529", "tags": []} for i in range(9)]
        assert len(_ev().find_related_memories(new, olds)) <= 5

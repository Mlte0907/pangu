"""盘古 ingestion.py 测试 — 核心写入路径"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pangu.core.palace import Drawer


class TestIngestion:
    """记忆摄入测试"""

    def test_remember_basic(self):
        from pangu.memory.ingestion import remember

        item_id, drawer = remember(
            raw_text="测试记忆内容",
            wing="test",
            room="e2e",
            importance=0.8,
            tags=["test"],
            author="test",
        )
        assert item_id is not None
        assert drawer.wing == "test"
        # 内容可能被加密
        assert drawer.content is not None

    def test_remember_empty_text(self):
        from pangu.memory.ingestion import remember

        try:
            remember(raw_text="", wing="test")
            raise AssertionError("Should raise ValueError")
        except ValueError:
            pass

    def test_remember_importance_range(self):
        from pangu.memory.ingestion import remember

        try:
            remember(raw_text="test", wing="test", importance=1.5)
            raise AssertionError("Should raise ValueError")
        except ValueError:
            pass

    def test_remember_with_embedding(self):
        from pangu.memory.ingestion import remember

        item_id, drawer = remember(
            raw_text="Python是AI首选编程语言",
            wing="test",
            importance=0.9,
            tags=["python"],
        )
        emb = drawer.metadata.get("embedding")
        assert emb is not None
        assert len(emb) == 384

    def test_cosine_similarity(self):
        from pangu.memory.ingestion import _cosine_similarity

        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert _cosine_similarity(a, b) == 1.0

        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_expand_query(self):
        from pangu.memory.retrieval import _expand_query

        drawers = [
            Drawer(id="1", content="Python编程", wing="test", tags=["python"]),
        ]
        result = _expand_query("py", drawers)
        assert "py" in result

"""盘古顶级智能验证 — 端到端集成测试

验证所有智能模块协同工作：
1. 情感智能 → 预测情绪 → 调整重要性
2. 自主学习 → 发现知识 → 生成假设 → 验证
3. 创造性思维 → 发现模式 → 生成原创想法
4. 跨领域迁移 → 发现跨域关联 → 知识迁移
5. 推理可视化 → 推理 → 展示推理过程
"""
import pytest
from pangu.core.palace import Drawer
from pangu.core.config import PanguConfig


@pytest.fixture
def config():
    return PanguConfig.load()


@pytest.fixture
def sample_drawers():
    return [
        Drawer(id="1", content="因为Python是AI首选语言，所以我们决定使用Python", wing="tech",
               importance=4.0, tags=["python", "ai", "language"]),
        Drawer(id="2", content="ONNX推理延迟0.002ms，性能优秀", wing="tech",
               importance=3.5, tags=["onnx", "perf", "inference"]),
        Drawer(id="3", content="FAISS向量搜索支持十亿级规模", wing="tech",
               importance=3.0, tags=["faiss", "vector", "search"]),
        Drawer(id="4", content="盘古记忆系统架构设计文档", wing="system",
               importance=4.5, tags=["pangu", "arch", "design"]),
        Drawer(id="5", content="这个功能有问题，需要紧急修复", wing="tech",
               importance=1.0, tags=["bug", "fix", "urgent"]),
        Drawer(id="6", content="团队协作提升了开发效率30%", wing="management",
               importance=3.8, tags=["team", "efficiency", "process"]),
        Drawer(id="7", content="因为测试覆盖不足，导致生产事故", wing="tech",
               importance=2.0, tags=["testing", "incident", "quality"]),
        Drawer(id="8", content="机器学习模型需要定期重训练", wing="ai",
               importance=3.2, tags=["ml", "retrain", "maintenance"]),
        Drawer(id="9", content="API设计遵循RESTful规范", wing="tech",
               importance=2.8, tags=["api", "restful", "design"]),
        Drawer(id="10", content="用户反馈系统体验很好", wing="product",
                importance=4.0, tags=["feedback", "ux", "positive"]),
    ]


class TestEmotionalIntelligencePipeline:
    """情感智能流水线"""

    def test_analyze_and_adjust(self, config, sample_drawers):
        from pangu.memory.emotional_intelligence import EmotionalIntelligence

        ei = EmotionalIntelligence(config)

        # 分析情绪
        result = ei.analyze_emotion("太棒了，项目成功上线！")
        assert result.emotion.value in ("positive", "excited")
        assert result.intensity > 0.5

        # 调整重要性
        drawer = sample_drawers[0]
        old_importance = drawer.importance
        new_importance = ei.adjust_importance(drawer, result)
        assert new_importance > old_importance

    def test_predict_and_recommend(self, config):
        from pangu.memory.emotional_intelligence import EmotionalIntelligence

        ei = EmotionalIntelligence(config)

        # 记录一些历史
        from pangu.memory.emotional_intelligence import EmotionResult, EmotionType
        for _ in range(5):
            ei.record_emotion("很好", EmotionResult(
                emotion=EmotionType.POSITIVE, intensity=0.8,
                keywords=["好"], confidence=0.8
            ))

        # 预测情绪
        prediction = ei.predict_emotion("继续开发")
        assert "prediction" in prediction
        assert "confidence" in prediction

        # 推荐交互
        recommendation = ei.recommend_interaction(prediction)
        assert isinstance(recommendation, str)
        assert len(recommendation) > 0


class TestAutonomousLearningPipeline:
    """自主学习流水线"""

    def test_discover_and_verify(self, config, sample_drawers):
        from pangu.memory.autonomous_learning import AutonomousLearning

        al = AutonomousLearning(config)

        # 发现知识
        discoveries = al.discover_knowledge(sample_drawers)
        assert len(discoveries) > 0

        # 生成假设
        hypotheses = al.generate_hypotheses(sample_drawers)
        assert len(hypotheses) > 0

        # 验证假设
        for h in hypotheses:
            result = al.verify_hypothesis(h, sample_drawers)
            assert result["status"] in ("verified", "rejected")

    def test_auto_learn_cycle(self, config, sample_drawers):
        from pangu.memory.autonomous_learning import AutonomousLearning

        al = AutonomousLearning(config)

        # 执行完整学习循环
        result = al.auto_learn(sample_drawers)
        assert "discoveries" in result
        assert "hypotheses_generated" in result
        assert "verified" in result
        assert "rejected" in result
        assert result["total_learning_cycles"] == 1

        # 再次执行
        result2 = al.auto_learn(sample_drawers)
        assert result2["total_learning_cycles"] == 2


class TestCreativeThinkingPipeline:
    """创造性思维流水线"""

    def test_discover_and_generate(self, config, sample_drawers):
        from pangu.memory.creative_thinking import CreativeThinking

        ct = CreativeThinking(config)

        # 发现模式
        patterns = ct.discover_patterns(sample_drawers)
        assert len(patterns) > 0

        # 生成想法
        ideas = ct.generate_ideas(sample_drawers)
        assert len(ideas) > 0

        # 生成原创想法
        novel = ct.generate_novel_ideas("tech", "AI 系统优化", sample_drawers)
        assert isinstance(novel, list)


class TestKnowledgeGraphPipeline:
    """知识图谱跨域迁移流水线"""

    def test_cross_domain_transfer(self, config, sample_drawers):
        from pangu.memory.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(config)

        # 添加实体
        kg.add_entity("Python", "Python语言", "technology", "AI首选编程语言")
        kg.add_entity("ONNX", "ONNX推理", "technology", "高性能推理框架")
        kg.add_entity("FAISS", "FAISS搜索", "technology", "向量搜索引擎")
        kg.add_entity("记忆系统", "盘古记忆", "concept", "AI记忆系统")

        # 添加关系
        kg.add_relation("r1", "Python", "used_for", "ONNX")
        kg.add_relation("r2", "ONNX", "used_for", "FAISS")

        # 跨域迁移
        result = kg.cross_domain_transfer("tech", "system")
        assert "source_domain" in result
        assert "target_domain" in result
        assert "transfers" in result


class TestGraphReasoningPipeline:
    """图推理可视化流水线"""

    def test_reasoning_visualization(self, config, sample_drawers):
        from pangu.memory.graph_reasoning import GraphReasoning

        gr = GraphReasoning(config)

        # 执行推理
        result = gr.infer("Python和ONNX的关系")
        assert result is not None

        # 可视化推理过程
        viz = gr.visualize_reasoning(result)
        assert "query" in viz
        assert "confidence" in viz
        assert "steps" in viz
        assert "entities" in viz
        assert "paths" in viz


class TestEndToEndIntelligence:
    """端到端智能集成测试"""

    def test_full_intelligence_cycle(self, config, sample_drawers):
        """完整智能循环：情感→学习→创造→迁移→推理"""
        from pangu.memory.emotional_intelligence import EmotionalIntelligence
        from pangu.memory.autonomous_learning import AutonomousLearning
        from pangu.memory.creative_thinking import CreativeThinking

        # 1. 情感智能：分析用户情绪
        ei = EmotionalIntelligence(config)
        emotion = ei.analyze_emotion("我很高兴看到系统在进步")
        assert emotion is not None

        # 2. 自主学习：从记忆中发现知识
        al = AutonomousLearning(config)
        discoveries = al.discover_knowledge(sample_drawers)
        assert len(discoveries) > 0

        # 3. 创造性思维：生成新想法
        ct = CreativeThinking(config)
        ideas = ct.generate_ideas(sample_drawers)
        assert len(ideas) > 0

        # 4. 所有模块独立运行，无冲突
        stats = al.get_learning_stats()
        assert "hypotheses" in stats
        assert "verified" in stats

"""盘古同义词扩展 — 搜索时自动扩展同义词，提升召回率"""

# 技术领域同义词
SYNONYM_MAP: dict[str, list[str]] = {
    # 编程语言
    "python": ["py", "python3", "python语言"],
    "java": ["java语言", "jdk"],
    "javascript": ["js", "es6", "typescript", "ts"],
    "golang": ["go", "go语言"],
    "rust": ["rust语言"],
    # AI/ML
    "ai": ["人工智能", "artificial intelligence", "机器智能"],
    "ml": ["机器学习", "machine learning", "统计学习"],
    "dl": ["深度学习", "deep learning", "神经网络"],
    "nlp": ["自然语言处理", "natural language processing", "文本处理"],
    "cv": ["计算机视觉", "computer vision", "图像处理"],
    "llm": ["大语言模型", "large language model", "大模型"],
    "transformer": ["transformer模型", "注意力模型"],
    # 框架/工具
    "pytorch": ["torch", "pytorch框架"],
    "tensorflow": ["tf", "tensorflow框架"],
    "keras": ["keras框架"],
    "sklearn": ["scikit-learn", "scikit"],
    "numpy": ["np", "numpy库"],
    "pandas": ["pd", "pandas库"],
    # 向量/搜索
    "faiss": ["faiss库", "向量搜索"],
    "ann": ["近似最近邻", "approximate nearest neighbor"],
    "embedding": ["嵌入", "向量表示", "向量编码"],
    "vector": ["向量", "矢量"],
    "similarity": ["相似度", "相似性"],
    "cosine": ["余弦相似度", "余弦"],
    # 神经网络
    "cnn": ["卷积神经网络", "convolutional neural network"],
    "rnn": ["循环神经网络", "recurrent neural network"],
    "lstm": ["长短期记忆", "long short-term memory"],
    "gan": ["生成对抗网络", "generative adversarial network"],
    "bert": ["bert模型", "双向编码器"],
    "gpt": ["gpt模型", "生成式预训练"],
    # 优化
    "sgd": ["随机梯度下降", "stochastic gradient descent"],
    "adam": ["adam优化器"],
    "lr": ["学习率", "learning rate"],
    "epoch": ["训练轮次", "迭代轮次"],
    "batch": ["批大小", "批次"],
    # 盘古相关
    "盘古": ["pangu", "盘古系统", "盘古记忆"],
    "伏羲": ["fuxi", "伏羲系统"],
    "记忆": ["memory", "记忆系统"],
    "衰减": ["decay", "遗忘", "淡化"],
    "巩固": ["consolidation", "强化"],
    "检索": ["recall", "搜索", "查询"],
    "嵌入": ["embedding", "向量", "编码"],
    "分词": ["tokenization", "tokenize", "分词器"],
    "索引": ["index", "索引器"],
    # 通用
    "优化": ["optimize", "调优", "改进"],
    "性能": ["performance", "效率", "速度"],
    "缓存": ["cache", "缓冲"],
    "并发": ["concurrency", "并行", "多线程"],
    "异步": ["async", "asynchronous", "非阻塞"],
    "部署": ["deploy", "上线", "发布"],
    "监控": ["monitor", "观测", "告警"],
    "日志": ["log", "logging", "记录"],
    "配置": ["config", "设置", "参数"],
    "测试": ["test", "testing", "验证"],
    "文档": ["doc", "documentation", "说明"],
}

# 反向索引：同义词 → 原词
_REVERSE_MAP: dict[str, str] = {}
for word, synonyms in SYNONYM_MAP.items():
    _REVERSE_MAP[word] = word
    for syn in synonyms:
        _REVERSE_MAP[syn.lower()] = word


def expand_synonyms(query: str, max_expansions: int = 3) -> list[str]:
    """扩展查询的同义词

    Args:
        query: 原始查询
        max_expansions: 最大扩展词数

    Returns:
        扩展后的词列表（含原词）
    """
    words = query.lower().split()
    expanded = set(words)

    for word in words:
        # 查找原词的同义词
        if word in SYNONYM_MAP:
            expanded.update(SYNONYM_MAP[word][:max_expansions])
        # 查找是否是某个词的同义词
        if word in _REVERSE_MAP:
            original = _REVERSE_MAP[word]
            expanded.update(SYNONYM_MAP.get(original, [])[:max_expansions])

    return list(expanded)[: max_expansions * len(words) + len(words)]


def get_synonyms(word: str) -> list[str]:
    """获取单个词的同义词"""
    word_lower = word.lower()
    if word_lower in SYNONYM_MAP:
        return SYNONYM_MAP[word_lower]
    if word_lower in _REVERSE_MAP:
        original = _REVERSE_MAP[word_lower]
        return [original] + [s for s in SYNONYM_MAP.get(original, []) if s != word_lower]
    return []

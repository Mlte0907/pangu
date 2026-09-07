"""盘古记忆脱敏器 — 记忆内容自动脱敏

从伏羲移植：在记忆与外部服务交互前自动脱敏敏感内容。
支持 minimal/standard/strict 三级脱敏，自动识别 XSS 攻击向量。

纯大脑能力：不做执行，只做数据清洗。
"""

import re


class MemorySanitizer:
    """记忆内容脱敏器 — 在记忆与外部服务交互前自动脱敏"""

    # 敏感信息模式（顺序很重要：长/具体模式必须先匹配）
    SENSITIVE_PATTERNS: dict[str, tuple[str, str]] = {
        "script_tag": (
            r"<script[^>]*>.*?</script>",
            "[SCRIPT_REMOVED]",
        ),
        "html_event": (
            r"\bon\w+\s*=\s*[\"'][^\"']*[\"']",
            "[HTML_EVENT_REMOVED]",
        ),
        "javascript_url": (
            r"javascript\s*:",
            "[JS_URL_REMOVED]",
        ),
        "iframe_tag": (
            r"<iframe[^>]*>.*?</iframe>",
            "[IFRAME_REMOVED]",
        ),
        "object_embed": (
            r"<(?:object|embed|applet)[^>]*>.*?</(?:object|embed|applet)>",
            "[EMBED_REMOVED]",
        ),
        "data_uri": (
            r"data\s*:\s*text/html[^\"'\s]*",
            "[DATA_URI_REMOVED]",
        ),
        "url_with_token": (
            r"https?://\S+[?&](token|key|secret|password|api_key|auth)=\S+",
            "[URL_WITH_CREDENTIAL]",
        ),
        "email": (r"[\w.-]+@[\w.-]+\.\w+", "[EMAIL]"),
        "ip_address": (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[IP]"),
        "id_card": (r"\d{17}[\dXx]", "[ID_CARD]"),
        "bank_card": (r"\d{16,19}", "[BANK_CARD]"),
        "phone": (r"1[3-9]\d{9}", "[PHONE]"),
    }

    # XSS 攻击模式
    XSS_PATTERNS: dict[str, tuple[str, str]] = {
        "script_tag": (r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "[SCRIPT_REMOVED]"),
        "script_tag_open": (r"<\s*script[^>]*>", "[SCRIPT_REMOVED]"),
        "html_event_quoted": (r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", "[HTML_EVENT_REMOVED]"),
        "html_event_unquoted": (r"\bon\w+\s*=\s*[^\s>\"']+", "[HTML_EVENT_REMOVED]"),
        "javascript_url": (r"javascript\s*:", "[JS_URL_REMOVED]"),
        "vbscript_url": (r"vbscript\s*:", "[VBSCRIPT_REMOVED]"),
        "css_expr": (r"\bexpression\s*\([^)]*\)", "[CSS_EXPR_REMOVED]"),
        "dangerous_tags": (
            r"<\s*(?:svg|img|body|input|iframe|object|embed|applet|form|button|meta|link|base|details|marquee|video|audio|source)\b[^>]*(?:on\w+|src\s*=\s*['\"]?javascript)[^>]*>",
            "[DANGEROUS_TAG_REMOVED]",
        ),
        "data_uri_xss": (r"data\s*:\s*(?:text/html|application/x-)[^\"'\s>]*", "[DATA_URI_REMOVED]"),
    }

    custom_keywords: list[str] = []

    @classmethod
    def sanitize(cls, text: str, level: str = "standard") -> tuple[str, dict]:
        """脱敏处理

        Args:
            text: 原始文本
            level: 脱敏级别 — minimal / standard / strict

        Returns:
            (脱敏后文本, {模式类型: 匹配数量})
        """
        sanitized = text
        redactions: dict = {}
        flags = re.IGNORECASE | re.DOTALL

        # 选择脱敏模式
        if level == "minimal":
            patterns = {"url_with_token": cls.SENSITIVE_PATTERNS["url_with_token"]}
        elif level == "strict":
            patterns = dict(cls.SENSITIVE_PATTERNS)
        else:  # standard
            patterns = {k: v for k, v in cls.SENSITIVE_PATTERNS.items() if k != "ip_address"}

        xss_patterns = {} if level == "minimal" else dict(cls.XSS_PATTERNS)
        all_patterns = {**xss_patterns, **patterns}

        for ptype, (pattern, replacement) in all_patterns.items():
            matches = re.findall(pattern, sanitized, flags)
            if matches:
                sanitized = re.sub(pattern, replacement, sanitized, flags=flags)
                redactions[ptype] = len(matches)

        # 自定义关键词
        for keyword in cls.custom_keywords:
            if keyword in sanitized:
                sanitized = sanitized.replace(keyword, f"[REDACTED:{keyword[:2]}***]")
                redactions[f"keyword:{keyword[:2]}"] = 1

        return sanitized, redactions

    @classmethod
    def sanitize_for_embedding(cls, text: str) -> str:
        """为嵌入 API 调用脱敏 — 保留语义但移除敏感数据"""
        sanitized, _ = cls.sanitize(text, level="standard")
        return sanitized

    @classmethod
    def sanitize_for_export(cls, text: str) -> str:
        """为导出脱敏 — 严格级别"""
        sanitized, _ = cls.sanitize(text, level="strict")
        return sanitized

    @classmethod
    def sanitize_for_llm(cls, text: str) -> str:
        """为 LLM 调用脱敏 — 最小级别，只移除最敏感信息"""
        sanitized, _ = cls.sanitize(text, level="minimal")
        return sanitized

    @classmethod
    def add_custom_keyword(cls, keyword: str):
        """添加自定义敏感词"""
        if keyword not in cls.custom_keywords:
            cls.custom_keywords.append(keyword)

    @classmethod
    def remove_custom_keyword(cls, keyword: str):
        """移除自定义敏感词"""
        if keyword in cls.custom_keywords:
            cls.custom_keywords.remove(keyword)

    @classmethod
    def get_redaction_summary(cls, text: str, level: str = "standard") -> dict:
        """获取脱敏摘要（不实际修改文本）"""
        _, redactions = cls.sanitize(text, level)
        return {
            "level": level,
            "total_redactions": sum(redactions.values()),
            "by_type": redactions,
            "has_xss": any(k in redactions for k in cls.XSS_PATTERNS),
            "has_pii": any(k in redactions for k in ["email", "phone", "id_card", "bank_card"]),
        }

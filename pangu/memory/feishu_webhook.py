"""盘古飞书 Webhook — 记忆事件自动推送到飞书群

支持：
- 文本消息推送
- 富文本卡片推送
- 事件过滤（只推送重要事件）
- 推送限流（防止刷屏）
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("pangu.memory.feishu_webhook")


class FeishuWebhook:
    """飞书 Webhook 推送"""

    # 只推送这些事件类型
    PUSH_EVENT_TYPES = {
        "memory.write", "memory.collect", "memory.quality_fix",
        "memory.delete", "memory.consolidate", "memory.forget",
    }

    def __init__(self, webhook_url: str = "", secret: str = ""):
        self.webhook_url = webhook_url
        self.secret = secret
        self._last_push_time: dict[str, float] = {}
        self._min_interval = 5  # 同类型事件最少间隔5秒

    def _gen_sign(self, timestamp: str) -> str:
        if not self.secret:
            return ""
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
        import base64
        return base64.b64encode(hmac_code).decode()

    def _should_push(self, event_type: str) -> bool:
        now = time.time()
        last = self._last_push_time.get(event_type, 0)
        if (now - last) < self._min_interval:
            return False
        self._last_push_time[event_type] = now
        return True

    def send_text(self, text: str) -> dict:
        if not self.webhook_url:
            return {"ok": False, "error": "webhook_url not configured"}

        import httpx
        timestamp = str(int(time.time()))
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        if self.secret:
            payload["timestamp"] = timestamp
            payload["sign"] = self._gen_sign(timestamp)

        try:
            resp = httpx.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                return {"ok": True}
            return {"ok": False, "error": result.get("msg", str(result))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def send_card(self, title: str, content_lines: list[str], color: str = "blue") -> dict:
        if not self.webhook_url:
            return {"ok": False, "error": "webhook_url not configured"}

        import httpx
        timestamp = str(int(time.time()))

        elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(content_lines)}}]

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        }

        payload = {"msg_type": "interactive", "card": card}
        if self.secret:
            payload["timestamp"] = timestamp
            payload["sign"] = self._gen_sign(timestamp)

        try:
            resp = httpx.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                return {"ok": True}
            return {"ok": False, "error": result.get("msg", str(result))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def push_event(self, event_type: str, memory_id: str = "", data: dict = None) -> dict:
        if event_type not in self.PUSH_EVENT_TYPES:
            return {"ok": False, "error": f"event {event_type} not in push list"}

        if not self._should_push(event_type):
            return {"ok": False, "error": "rate limited"}

        icons = {
            "memory.write": "📝", "memory.collect": "📥",
            "memory.quality_fix": "✨", "memory.delete": "🗑️",
            "memory.consolidate": "🔄", "memory.forget": "🧹",
        }
        icon = icons.get(event_type, "📌")
        time_str = datetime.now().strftime("%H:%M:%S")

        lines = [f"**事件**: {icon} {event_type}"]
        if memory_id:
            lines.append(f"**记忆ID**: `{memory_id}`")
        if data:
            for k, v in list(data.items())[:5]:
                lines.append(f"**{k}**: {str(v)[:100]}")
        lines.append(f"**时间**: {time_str}")

        return self.send_card(f"{icon} 盘古记忆事件", lines, color="blue")

    def is_configured(self) -> bool:
        return bool(self.webhook_url)


_feishu: FeishuWebhook | None = None


def get_feishu_webhook(webhook_url: str = "", secret: str = "") -> FeishuWebhook:
    global _feishu
    if _feishu is None:
        _feishu = FeishuWebhook(webhook_url, secret)
    return _feishu

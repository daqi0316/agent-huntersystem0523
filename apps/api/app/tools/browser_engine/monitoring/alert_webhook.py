"""
告警通知通道 — 飞书 / Slack Webhook
引擎降级 / 不可达时触发
"""

from __future__ import annotations

import json
import structlog
from typing import Literal
from urllib.request import Request, urlopen
from urllib.error import URLError

from .. import EngineType, EngineStatus

logger = structlog.get_logger()


class AlertWebhook:
    """
    告警通知通道
    支持：飞书（Lark） / Slack
    """

    def __init__(
        self,
        webhook_url: str,
        channel: Literal["feishu", "slack"] = "feishu",
        source_name: str = "browser-engine",
    ):
        self._webhook_url = webhook_url
        self._channel = channel
        self._source = source_name

    # ── 引擎事件 ──

    def send_engine_unavailable(
        self,
        engine_type: EngineType,
    ) -> bool:
        """引擎不可达告警"""
        title = f"[{self._source}] 引擎不可达"
        text = f"引擎 {engine_type.value} 状态变为 UNAVAILABLE，将触发降级链。"
        return self._send(title, text, severity="critical")

    def send_engine_recovered(
        self,
        engine_type: EngineType,
    ) -> bool:
        """引擎恢复通知"""
        title = f"[{self._source}] 引擎已恢复"
        text = f"引擎 {engine_type.value} 恢复 AVAILABLE。"
        return self._send(title, text, severity="info")

    def send_fallback_alert(
        self,
        platform: str,
        from_engine: EngineType,
        to_engine: EngineType,
    ) -> bool:
        """降级告警"""
        title = f"[{self._source}] 引擎降级"
        text = f"平台 {platform}: {from_engine.value} → {to_engine.value}"
        return self._send(title, text, severity="warning")

    def send_health_summary(
        self,
        results: dict[EngineType, EngineStatus],
    ) -> bool:
        """健康检查汇总（定期发送）"""
        available = sum(1 for s in results.values() if s == EngineStatus.AVAILABLE)
        total = len(results)
        lines = [
            f"• {k.value}: {v.value}"
            for k, v in results.items()
        ]
        title = f"[{self._source}] 引擎健康报告 ({available}/{total})"
        text = "\n".join(lines)
        severity = "critical" if available == 0 else "warning" if available < total else "info"
        return self._send(title, text, severity=severity)

    # ── 底层发送 ──

    def _send(self, title: str, text: str, severity: str = "info") -> bool:
        """发送消息到配置的 webhook"""
        try:
            payload = self._build_payload(title, text, severity)
            data = json.dumps(payload).encode("utf-8")
            req = Request(
                self._webhook_url,
                data=data,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                logger.info("告警发送成功", channel=self._channel, title=title, response=body)
                return True
        except (URLError, OSError, json.JSONEncodeError) as e:
            logger.error("告警发送失败", channel=self._channel, title=title, error=str(e))
            return False

    def _build_payload(self, title: str, text: str, severity: str) -> dict:
        """根据 channel 构建消息体"""
        if self._channel == "feishu":
            color_map = {"critical": "red", "warning": "yellow", "info": "green"}
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": color_map.get(severity, "blue"),
                    },
                    "elements": [
                        {"tag": "markdown", "content": text},
                        {
                            "tag": "note",
                            "elements": [
                                {"tag": "plain_text", "content": f"来源: {self._source} | severity: {severity}"}
                            ],
                        },
                    ],
                },
            }
        else:
            color_map = {"critical": "#FF0000", "warning": "#FFA500", "info": "#36a64f"}
            return {
                "attachments": [
                    {
                        "color": color_map.get(severity, "#36a64f"),
                        "blocks": [
                            {
                                "type": "header",
                                "text": {"type": "plain_text", "text": title},
                            },
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": text},
                            },
                            {
                                "type": "context",
                                "elements": [
                                    {"type": "mrkdwn", "text": f"来源: `{self._source}` | 级别: `{severity}`"}
                                ],
                            },
                        ],
                    }
                ],
            }


__all__ = ["AlertWebhook"]

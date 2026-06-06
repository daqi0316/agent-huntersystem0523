"""Time tool — 获取当前日期时间（v4 加 Pydantic InputModel）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.metadata import Capability, register_tool


SUPPORTED_TIMEZONES = (
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Hong_Kong",
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "UTC",
)


class GetCurrentTimeInput(BaseModel):
    """get_current_time tool 输入。"""

    timezone: Literal[
        "Asia/Shanghai",
        "Asia/Tokyo",
        "Asia/Hong_Kong",
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Paris",
        "UTC",
    ] = Field(default="Asia/Shanghai", description="时区（默认 Asia/Shanghai）")


async def _handle_get_current_time(timezone: str = "Asia/Shanghai") -> str:
    tz_map = {
        "Asia/Shanghai": 8,
        "Asia/Tokyo": 9,
        "Asia/Hong_Kong": 8,
        "America/New_York": -5,
        "America/Los_Angeles": -8,
        "Europe/London": 0,
        "Europe/Paris": 1,
        "UTC": 0,
    }
    offset = tz_map.get(timezone, 8)
    now = datetime.now(timezone.utc) + timedelta(hours=offset)
    return f"当前时间 ({timezone}): {now.strftime('%Y-%m-%d %H:%M:%S')}"


register_tool(
    "get_current_time",
    retryable=True,
    max_retries=1,
    capability=Capability.READ,
    input_model=GetCurrentTimeInput,
    description="获取当前服务器的日期和时间（支持 8 个时区）。",
    version="1.0.0",
    handler=_handle_get_current_time,
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前服务器的日期和时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": (
                            "时区（可选，默认 Asia/Shanghai）。支持的时区: "
                            "Asia/Shanghai, Asia/Tokyo, Asia/Hong_Kong, "
                            "America/New_York, America/Los_Angeles, "
                            "Europe/London, Europe/Paris, UTC"
                        ),
                        "default": "Asia/Shanghai",
                    },
                },
            },
        },
    },
]

handlers = {"get_current_time": _handle_get_current_time}

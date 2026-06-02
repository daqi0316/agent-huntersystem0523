"""Time tool — 获取当前日期时间，支持时区。"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta


async def _handle_get_current_time(tz_name: str = "Asia/Shanghai") -> str:
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
    offset = tz_map.get(tz_name, 8)
    now = datetime.now(timezone.utc) + timedelta(hours=offset)
    return f"当前时间 ({tz_name}): {now.strftime('%Y-%m-%d %H:%M:%S')}"


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
                        "description": "时区（可选，默认 Asia/Shanghai）。支持的时区: Asia/Shanghai, Asia/Tokyo, Asia/Hong_Kong, America/New_York, America/Los_Angeles, Europe/London, Europe/Paris, UTC",
                        "default": "Asia/Shanghai",
                    },
                },
            },
        },
    },
]

handlers = {"get_current_time": _handle_get_current_time}

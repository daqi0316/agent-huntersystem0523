"""天气查询 Skill — 使用 wttr.in 获取实时天气。"""

import logging

import httpx

from app.skills.base import Skill

logger = logging.getLogger(__name__)

_WTTR_URL = "https://wttr.in/{location}?format=j1"

_TOOL_WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取某个城市或地点的实时天气情况，包括温度、湿度、风速、天气状况等。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "城市或地点名称，支持中文，如「北京」「Shanghai」「Tokyo」",
                },
            },
            "required": ["location"],
        },
    },
}


async def _get_weather(location: str) -> dict:
    """从 wttr.in 查询天气。"""
    url = _WTTR_URL.format(location=location)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    # 提取关键信息
    current = data.get("current_condition", [{}])[0]
    weather_info = {
        "location": location,
        "temp_c": current.get("temp_C", "N/A"),
        "feels_like_c": current.get("FeelsLikeC", "N/A"),
        "humidity": current.get("humidity", "N/A"),
        "wind_speed_kmh": current.get("windspeedKmph", "N/A"),
        "wind_dir": current.get("winddir16Point", "N/A"),
        "weather_desc": current.get("weatherDesc", [{}])[0].get("value", "N/A"),
        "visibility_km": current.get("visibility", "N/A"),
        "pressure_mb": current.get("pressure", "N/A"),
    }
    return weather_info


class WeatherSkill(Skill):
    """天气查询技能。"""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "实时天气查询，支持全球城市"

    def get_tools(self) -> list[dict]:
        return [_TOOL_WEATHER]

    def get_handlers(self) -> dict:
        return {"get_weather": _get_weather}


skill = WeatherSkill()

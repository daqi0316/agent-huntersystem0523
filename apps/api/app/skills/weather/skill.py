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
        "description": "获取某个城市或地点的天气情况，支持今天/明天/后天的预报。包括温度、体感温度、湿度、风速、天气状况、紫外线指数、PM2.5等。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "城市或地点名称，支持中文，如「佛山」「北京」「Shanghai」「Tokyo」",
                },
                "days": {
                    "type": "integer",
                    "description": "预报天数。0=今天（默认，实时天气），1=明天，2=后天",
                    "default": 0,
                },
            },
            "required": ["location"],
        },
    },
}


async def _get_weather(location: str, days: int = 0) -> dict:
    """从 wttr.in 查询天气。days=0=今天, 1=明天, 2=后天."""
    url = _WTTR_URL.format(location=location)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    # 提取关键信息
    current = data.get("current_condition", [{}])[0]
    # wttr.in 的 J1 格式: nearest_area 有地区信息, weather 有未来3天
    nearest = data.get("nearest_area", [{}])[0] if data.get("nearest_area") else {}
    area_desc = nearest.get("areaName", [{}])[0].get("value", location)
    country = nearest.get("country", [{}])[0].get("value", "")

    weather_info = {
        "location": area_desc,
        "country": country,
        "temp_c": current.get("temp_C", "N/A"),
        "feels_like_c": current.get("FeelsLikeC", "N/A"),
        "humidity": current.get("humidity", "N/A"),
        "wind_speed_kmh": current.get("windspeedKmph", "N/A"),
        "wind_dir": current.get("winddir16Point", "N/A"),
        "weather_desc": current.get("weatherDesc", [{}])[0].get("value", "N/A"),
        "visibility_km": current.get("visibility", "N/A"),
        "pressure_mb": current.get("pressure", "N/A"),
        "uv_index": current.get("UVIndex", "N/A"),
        "pollution": data.get("weather", [{}])[0].get("airQuality", {}).get("pm2_5", "N/A")
        if data.get("weather") else "N/A",
    }

    # 如果查明天或后天，同时返回天气预报
    if days >= 1 and data.get("weather"):
        future = data["weather"][min(days, len(data["weather"]) - 1)]
        future_date = future.get("date", "")
        max_temp = future.get("maxtempC", "N/A")
        min_temp = future.get("mintempC", "N/A")
        desc = future.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", future.get("desc", ""))
        weather_info["forecast"] = {
            "date": future_date,
            "max_temp_c": max_temp,
            "min_temp_c": min_temp,
            "description": desc,
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

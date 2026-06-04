"""天气查询 Skill — 使用 Open-Meteo（公开 API、无需 key）。"""

import asyncio
import logging
from typing import Any

import httpx

from app.skills.base import Skill

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_TIMEOUT = 15.0
_MAX_ATTEMPTS = 3

_TOOL_WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "获取某个城市或地点的天气情况，支持今天/明天/后天的预报。"
            "包括温度、体感温度、湿度、风速、天气状况、紫外线指数。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "城市或地点名称，支持中文（如「佛山」「上海」）或英文（如「Foshan」「Tokyo」）",
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


# WMO 天气代码 → 中文描述（Open-Meteo 标准）
# https://open-meteo.com/en/docs#weather_variable_documentation
_WMO_CODE_DESC = {
    0: "晴", 1: "基本晴朗", 2: "局部多云", 3: "阴",
    45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "中等毛毛雨", 55: "密集毛毛雨",
    56: "冻毛毛雨", 57: "密集冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "密集冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "中阵雨", 82: "密集阵雨",
    85: "小阵雪", 86: "密集阵雪",
    95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴大冰雹",
}


def _pick_best_geo_result(results: list[dict]) -> dict | None:
    """Open-Meteo geocode 多个结果时按 admin 级别 + 人口选最佳。

    例：「佛山」会同时匹配广东佛山（PPLA2, 人口 9M）和云南佛山（PPLA4, 人口少），
    应优先选广东佛山。

    排序：feature_code 级别升序 → 人口降序 → 海拔升序
    """
    if not results:
        return None

    admin_rank = {
        "PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3,
        "PPLA4": 4, "PPL": 5,
    }

    def sort_key(r: dict) -> tuple[int, int, float]:
        rank = admin_rank.get(r.get("feature_code", "PPL"), 99)
        pop = r.get("population") or 0
        elev = r.get("elevation") or 0
        return (rank, -pop, elev)

    return sorted(results, key=sort_key)[0]


async def _geocode(client: httpx.AsyncClient, location: str) -> dict:
    is_chinese = any("\u4e00" <= c <= "\u9fff" for c in location)
    params = {
        "name": location,
        "count": 5,
        "language": "zh" if is_chinese else "en",
    }
    resp = await client.get(_GEOCODE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        raise ValueError(f"找不到城市：{location}")
    best = _pick_best_geo_result(results)
    if best is None:
        raise ValueError(f"找不到城市：{location}")
    return {
        "lat": best["latitude"],
        "lon": best["longitude"],
        "name": best.get("name", location),
        "country": best.get("country", ""),
        "admin1": best.get("admin1", ""),
        "timezone": best.get("timezone", "auto"),
    }


async def _fetch_forecast(
    client: httpx.AsyncClient, lat: float, lon: float, timezone: str
) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m", "apparent_temperature",
            "relative_humidity_2m", "wind_speed_10m",
            "wind_direction_10m", "weather_code",
        ]),
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "sunrise", "sunset", "uv_index_max",
        ]),
        "timezone": timezone,
        "forecast_days": 3,
    }
    resp = await client.get(_FORECAST_URL, params=params)
    resp.raise_for_status()
    return resp.json()


async def _get_weather(location: str, days: int = 0) -> dict:
    days = max(0, min(days, 2))

    last_error: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                geo = await _geocode(client, location)
                data = await _fetch_forecast(client, geo["lat"], geo["lon"], geo["timezone"])

            current = data.get("current", {})
            daily = data.get("daily", {})
            current_code = current.get("weather_code", -1)

            result: dict[str, Any] = {
                "location": geo["name"],
                "region": geo["admin1"],
                "country": geo["country"],
                "current": {
                    "temp_c": current.get("temperature_2m"),
                    "feels_like_c": current.get("apparent_temperature"),
                    "humidity_pct": current.get("relative_humidity_2m"),
                    "wind_kmh": current.get("wind_speed_10m"),
                    "wind_dir": current.get("wind_direction_10m"),
                    "desc": _WMO_CODE_DESC.get(current_code, f"代码{current_code}"),
                },
            }

            if days >= 1 and daily.get("time"):
                idx = min(days, len(daily["time"]) - 1)
                future_code = daily["weather_code"][idx]
                result["forecast"] = {
                    "date": daily["time"][idx],
                    "max_temp_c": daily["temperature_2m_max"][idx],
                    "min_temp_c": daily["temperature_2m_min"][idx],
                    "desc": _WMO_CODE_DESC.get(future_code, f"代码{future_code}"),
                    "uv_index_max": daily.get("uv_index_max", [None] * 3)[idx],
                    "sunrise": daily.get("sunrise", [None] * 3)[idx],
                    "sunset": daily.get("sunset", [None] * 3)[idx],
                }

            return result

        except httpx.TimeoutException as e:
            last_error = f"网络超时（{_TIMEOUT}s）"
            logger.warning("get_weather attempt %d/%d timeout: %s", attempt, _MAX_ATTEMPTS, e)
        except httpx.HTTPStatusError as e:
            last_error = f"上游 HTTP {e.response.status_code}"
            logger.warning("get_weather attempt %d/%d http %s", attempt, _MAX_ATTEMPTS, e.response.status_code)
        except ValueError as e:
            return {"error": {"code": "location_not_found", "message": str(e), "location": location}}
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning("get_weather attempt %d/%d failed: %s", attempt, _MAX_ATTEMPTS, e)

        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

    return {
        "error": {
            "code": "upstream_unavailable",
            "message": f"天气服务暂时不可达：{last_error}。已重试 {_MAX_ATTEMPTS} 次。",
            "attempts": _MAX_ATTEMPTS,
        }
    }


class WeatherSkill(Skill):
    """天气查询技能。"""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "实时天气查询（Open-Meteo，公开 API），支持全球城市"

    def get_tools(self) -> list[dict]:
        return [_TOOL_WEATHER]

    def get_handlers(self) -> dict:
        return {"get_weather": _get_weather}


skill = WeatherSkill()

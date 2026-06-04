"""天气查询 Skill。

三级 fallback：
  1) QWeather dev API（最快，结构化数据，X-QW-Api-Key 鉴权）
  2) wttr.in（无 key，间歇性 SSL，偶尔通）
  3) Tavily web_search（最稳，搜真实页面，LLM 解析）

设计：QWeather 用 lat/lon 直查（Geo API 400），
城市名 → 经纬度 内置表，命中直接查，没命中降级到 wttr/web_search。
"""

import asyncio
import logging
import os
from typing import Any

import httpx

from app.skills.base import Skill
from app.core.config import settings

logger = logging.getLogger(__name__)

_WTTR_URL = "https://wttr.in/{loc}?format=j1"
_TIMEOUT = 8.0
_OVERALL_TIMEOUT = 15.0

_CITY_COORDS: dict[str, tuple[float, float]] = {
    "佛山": (113.13148, 23.02677), "广州": (113.26436, 23.12908),
    "深圳": (114.05786, 22.54310), "东莞": (113.75178, 23.02067),
    "珠海": (113.57668, 22.27073), "中山": (113.38239, 22.51595),
    "惠州": (114.41636, 23.11153), "江门": (113.08160, 22.57865),
    "北京": (116.40529, 39.90499), "上海": (121.47370, 31.23037),
    "天津": (117.19019, 39.12554), "重庆": (106.55073, 29.56471),
    "杭州": (120.15507, 30.27415), "南京": (118.79688, 32.06026),
    "苏州": (120.58532, 31.29889), "武汉": (114.30554, 30.59276),
    "成都": (104.06680, 30.57296), "西安": (108.93984, 34.34192),
    "青岛": (120.38264, 36.06711), "济南": (117.12010, 36.65121),
    "厦门": (118.08948, 24.47983), "福州": (119.29650, 26.07451),
    "昆明": (102.83294, 24.88015), "大理": (100.22570, 25.59690),
    "长沙": (112.93886, 28.22778), "郑州": (113.62536, 34.74660),
    "Foshan": (113.13148, 23.02677), "Guangzhou": (113.26436, 23.12908),
    "Shenzhen": (114.05786, 22.54310), "Beijing": (116.40529, 39.90499),
    "Shanghai": (121.47370, 31.23037), "Tokyo": (139.69171, 35.68949),
    "Hong Kong": (114.16936, 22.31930),
}

_QWEATHER_CODE_DESC: dict[str, str] = {
    "CLEAR_DAY": "晴", "CLEAR_NIGHT": "晴",
    "PARTLY_CLOUDY_DAY": "多云", "PARTLY_CLOUDY_NIGHT": "多云",
    "CLOUDY": "阴", "LIGHT_HAZE": "轻度雾霾", "MODERATE_HAZE": "中度雾霾",
    "HEAVY_HAZE": "重度雾霾",
    "LIGHT_RAIN": "小雨", "MODERATE_RAIN": "中雨", "HEAVY_RAIN": "大雨",
    "STORM_RAIN": "暴雨", "FROST_RAIN": "冻雨",
    "LIGHT_SNOW": "小雪", "MODERATE_SNOW": "中雪", "HEAVY_SNOW": "大雪",
    "STORM_SNOW": "暴雪", "DUST": "浮尘", "SAND": "沙尘", "WIND": "大风",
    "FOG": "雾", "HAZE": "霾", "THUNDER_SHOWER": "雷阵雨",
    "HAIL": "冰雹", "SLEET": "雨夹雪", "SNOW": "雪", "RAIN": "雨",
    "DRIZZLE": "毛毛雨", "SHOWER_RAIN": "阵雨",
}

_TOOL_WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取某个城市或地点的天气情况，支持今天/明天/后天的预报。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "城市或地点名称"},
                "days": {"type": "integer", "description": "0=今天,1=明天,2=后天", "default": 0},
            },
            "required": ["location"],
        },
    },
}


def _qweather_host() -> str:
    return (settings.qweather_api_host or os.getenv("QWEATHER_API_HOST", "")).strip().rstrip("/")


def _qweather_key() -> str:
    return (settings.qweather_api_key or os.getenv("QWEATHER_API_KEY", "")).strip()


def _resolve_location(location: str) -> tuple[float, float, str] | None:
    if location in _CITY_COORDS:
        lon, lat = _CITY_COORDS[location]
        return (lon, lat, location)
    for key, coords in _CITY_COORDS.items():
        if location in key or key in location:
            return (coords[0], coords[1], key)
    return None


async def _qweather_now(client: httpx.AsyncClient, lat: float, lon: float, key: str, host: str) -> dict:
    params = {"location": f"{lon:.5f},{lat:.5f}", "lang": "zh"}
    resp = await client.get(
        f"https://{host}/v7/weather/now",
        params=params, headers={"X-QW-Api-Key": key}, timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200":
        raise ValueError(f"QWeather 实时：code={data.get('code')}, {data.get('code', '?')}")
    return data.get("now", {})


async def _qweather_3d(client: httpx.AsyncClient, lat: float, lon: float, key: str, host: str) -> list:
    params = {"location": f"{lon:.5f},{lat:.5f}", "lang": "zh"}
    resp = await client.get(
        f"https://{host}/v7/weather/3d",
        params=params, headers={"X-QW-Api-Key": key}, timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200":
        raise ValueError(f"QWeather 预报：code={data.get('code')}")
    return data.get("daily", [])


def _format_qweather(loc_name: str, now: dict, daily: list, days: int) -> dict:
    code = now.get("icon", "999")
    desc = _QWEATHER_CODE_DESC.get(code, now.get("text", code))
    result: dict[str, Any] = {
        "location": loc_name,
        "current": {
            "temp_c": now.get("temp"),
            "feels_like_c": now.get("feelsLike"),
            "humidity_pct": now.get("humidity"),
            "wind_kmh": now.get("windSpeed"),
            "wind_dir": now.get("windDir"),
            "pressure_hpa": now.get("pressure"),
            "visibility_km": now.get("vis"),
            "desc": desc,
            "obs_time": now.get("obsTime"),
        },
    }
    if days >= 1 and daily:
        idx = max(0, min(days, len(daily) - 1))
        d = daily[idx]
        result["forecast"] = {
            "date": d.get("fxDate"),
            "max_temp_c": d.get("tempMax"),
            "min_temp_c": d.get("tempMin"),
            "desc": _QWEATHER_CODE_DESC.get(d.get("iconDay", "999"), d.get("textDay", "?")),
            "uv_index": d.get("uvIndex"),
        }
    return result


async def _qweather_weather(location: str, days: int) -> dict:
    key = _qweather_key()
    host = _qweather_host()
    if not key or not host:
        return {"error": {"code": "no_credentials", "message": "QWEATHER_API_KEY / QWEATHER_API_HOST 未配置"}}
    resolved = _resolve_location(location)
    if not resolved:
        return {"error": {"code": "unknown_location", "message": f"暂不支持 {location}（表内没经纬度），降级其他源"}}
    lon, lat, loc_name = resolved
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        now = await _qweather_now(client, lat, lon, key, host)
        daily = await _qweather_3d(client, lat, lon, key, host) if days >= 1 else []
    return _format_qweather(loc_name, now, daily, days)


def _format_search_as_weather(search_results: list, location: str, days: int) -> dict:
    if not search_results or "error" in search_results[0]:
        return {"error": {"code": "search_failed", "message": str(search_results[0].get("error", "无结果")) if search_results else "无结果"}}
    answer = search_results[0].get("answer", "")
    sources = search_results[0].get("sources", [])
    label = {0: "今天", 1: "明天", 2: "后天"}.get(days, f"{days}天后")
    parts = [f"【{label}{location}天气（来自网络搜索）】"]
    if answer:
        parts.append(answer[:500])
    for s in sources[:3]:
        title = s.get("title", "")
        content = s.get("content", "")
        if title or content:
            parts.append(f"• {title}: {content[:150]}")
    return {
        "location": location,
        "current": {"desc": f"见下方搜索结果（{label}）"},
        "forecast_note": "\n".join(parts),
        "source": "web_search",
    }


async def _web_search_weather(location: str, days: int) -> dict:
    label = {0: "今天", 1: "明天", 2: "后天"}.get(days, f"{days}天后")
    query = f"{location} {label}天气 预报 温度"
    try:
        from app.skills.web_search.skill import _web_search
        results = await _web_search(query, max_results=3)
        return _format_search_as_weather(results, location, days)
    except Exception as e:
        return {"error": {"code": "web_search_failed", "message": f"网络搜索失败：{e}"}}


async def _wttr_weather(client: httpx.AsyncClient, location: str, days: int) -> dict:
    url = _WTTR_URL.format(loc=location)
    resp = await client.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    current = data.get("current_condition", [{}])[0]
    nearest = (data.get("nearest_area") or [{}])[0]
    area_desc = (nearest.get("areaName") or [{}])[0].get("value", location)
    country = (nearest.get("country") or [{}])[0].get("value", "")
    result: dict[str, Any] = {
        "location": area_desc,
        "country": country,
        "current": {
            "temp_c": current.get("temp_C"),
            "feels_like_c": current.get("FeelsLikeC"),
            "humidity_pct": current.get("humidity"),
            "wind_kmh": current.get("windspeedKmph"),
            "desc": (current.get("weatherDesc") or [{}])[0].get("value", "未知"),
        },
    }
    if days >= 1 and data.get("weather"):
        idx = max(0, min(days, len(data["weather"]) - 1))
        future = data["weather"][idx]
        hourly4 = (future.get("hourly") or [{}])[4] if future.get("hourly") else {}
        result["forecast"] = {
            "date": future.get("date"),
            "max_temp_c": future.get("maxtempC"),
            "min_temp_c": future.get("mintempC"),
            "desc": (hourly4.get("weatherDesc") or [{}])[0].get("value", "未知"),
        }
    return result


async def _wttr_weather_entry(location: str, days: int) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await _wttr_weather(client, location, days)


async def _get_weather(location: str, days: int = 0) -> dict:
    days = max(0, min(days, 2))

    qw = await _qweather_weather(location, days)
    if qw and not qw.get("error"):
        return qw
    qw_err = qw.get("error", {}).get("message", "?")

    try:
        wt = await _wttr_weather_entry(location, days)
        if wt and not wt.get("error"):
            return wt
    except Exception:
        pass

    sw = await _web_search_weather(location, days)
    if sw and not sw.get("error"):
        return sw

    return {
        "error": {
            "code": "upstream_unavailable",
            "message": f"天气服务暂时不可达：QWeather: {qw_err}。建议查看手机自带天气或访问中国天气网。",
        }
    }


class WeatherSkill(Skill):
    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "实时天气查询（和风天气 QWeather，国内 CDN），支持全球城市"

    def get_tools(self) -> list[dict]:
        return [_TOOL_WEATHER]

    def get_handlers(self) -> dict:
        return {"get_weather": _get_weather}


skill = WeatherSkill()

"""天气查询 Skill — 和风天气（QWeather，国内 CDN）主 + wttr.in 兜底。

主源：QWeather dev API（geoapi.qweather.com + devapi.qweather.com）
  - 国内 CDN，稳定
  - 需 API Key：https://console.qweather.com 注册（免费 1000 次/天）
  - 配置：QWEATHER_API_KEY（空则跳过主源）

兜底：wttr.in
  - 无 key，但 SSL 不稳
  - 偶尔成功

设计原因（2026-06 教训）：
  - api.open-meteo.com 在用户网络 DNS 解析到德国 Hetzner IP，TLS 握手 hang
  - 之前用 wttr.in 也 SSL_ERROR_SYSCALL
  - QWeather 国内 CDN，0.2s 响应（实测），最适合国内环境
"""

import asyncio
import logging
import os
from typing import Any

import httpx

from app.skills.base import Skill
from app.core.config import settings

logger = logging.getLogger(__name__)

_QWEATHER_GEO_URL = "https://geoapi.qweather.com/v2/city/lookup"
_QWEATHER_NOW_URL = "https://devapi.qweather.com/v7/weather/now"
_QWEATHER_3D_URL = "https://devapi.qweather.com/v7/weather/3d"
_WTTR_URL = "https://wttr.in/{loc}?format=j1"

_TIMEOUT = 8.0
_OVERALL_TIMEOUT = 15.0

# QWeather 天气现象代码 → 中文
_QWEATHER_CODE_DESC = {
    "CLEAR_DAY": "晴", "CLEAR_NIGHT": "晴",
    "PARTLY_CLOUDY_DAY": "多云", "PARTLY_CLOUDY_NIGHT": "多云",
    "CLOUDY": "阴", "LIGHT_HAZE": "轻度雾霾", "MODERATE_HAZE": "中度雾霾",
    "HEAVY_HAZE": "重度雾霾",
    "LIGHT_RAIN": "小雨", "MODERATE_RAIN": "中雨", "HEAVY_RAIN": "大雨",
    "STORM_RAIN": "暴雨", "FROST_RAIN": "冻雨",
    "LIGHT_SNOW": "小雪", "MODERATE_SNOW": "中雪", "HEAVY_SNOW": "大雪",
    "STORM_SNOW": "暴雪",
    "DUST": "浮尘", "SAND": "沙尘", "WIND": "大风",
    "FOG": "雾", "HAZE": "霾", "THUNDER_SHOWER": "雷阵雨",
    "HAIL": "冰雹", "SLEET": "雨夹雪", "SNOW": "雪", "RAIN": "雨",
    "DRIZZLE": "毛毛雨", "SHOWER_RAIN": "阵雨",
}

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


def _get_qweather_key() -> str:
    return (settings.qweather_api_key or os.getenv("QWEATHER_API_KEY", "")).strip()


async def _qweather_lookup_location(client: httpx.AsyncClient, location: str, key: str) -> dict:
    is_chinese = any("\u4e00" <= c <= "\u9fff" for c in location)
    params = {"location": location, "key": key, "lang": "zh" if is_chinese else "en", "number": 1}
    resp = await client.get(_QWEATHER_GEO_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200":
        raise ValueError(f"QWeather 城市查询失败：code={data.get('code')}, {location}")
    locs = data.get("location") or []
    if not locs:
        raise ValueError(f"找不到城市：{location}")
    loc = locs[0]
    return {
        "id": loc["id"],
        "name": loc.get("name", location),
        "adm1": loc.get("adm1", ""),
        "adm2": loc.get("adm2", ""),
        "country": loc.get("country", ""),
    }


async def _qweather_now(client: httpx.AsyncClient, loc_id: str, key: str) -> dict:
    params = {"location": loc_id, "key": key, "lang": "zh"}
    resp = await client.get(_QWEATHER_NOW_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200":
        raise ValueError(f"QWeather 实时天气失败：code={data.get('code')}")
    return data.get("now", {})


async def _qweather_3d(client: httpx.AsyncClient, loc_id: str, key: str) -> list:
    params = {"location": loc_id, "key": key, "lang": "zh"}
    resp = await client.get(_QWEATHER_3D_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200":
        raise ValueError(f"QWeather 预报失败：code={data.get('code')}")
    return data.get("daily", [])


def _format_qweather(loc: dict, now: dict, daily: list, days: int) -> dict:
    code = now.get("icon", "999")
    desc = _QWEATHER_CODE_DESC.get(code, code)
    result: dict[str, Any] = {
        "location": loc["name"],
        "region": loc.get("adm2") or loc.get("adm1", ""),
        "country": loc.get("country", ""),
        "current": {
            "temp_c": now.get("temp"),
            "feels_like_c": now.get("feelsLike"),
            "humidity_pct": now.get("humidity"),
            "wind_kmh": now.get("windSpeed"),
            "wind_dir": now.get("windDir"),
            "pressure_hpa": now.get("pressure"),
            "visibility_km": now.get("vis"),
            "desc": desc,
        },
    }
    if days >= 1 and daily:
        idx = max(0, min(days, len(daily) - 1))
        d = daily[idx]
        result["forecast"] = {
            "date": d.get("fxDate"),
            "max_temp_c": d.get("tempMax"),
            "min_temp_c": d.get("tempMin"),
            "desc": _QWEATHER_CODE_DESC.get(d.get("iconDay", "999"), d.get("iconDay", "?")),
            "uv_index": d.get("uvIndex"),
        }
    return result


async def _qweather_weather(location: str, days: int) -> dict:
    key = _get_qweather_key()
    if not key:
        return {"error": {"code": "no_api_key", "message": "QWEATHER_API_KEY 未配置（请去 https://console.qweather.com 注册免费 key）"}}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        loc = await _qweather_lookup_location(client, location, key)
        now = await _qweather_now(client, loc["id"], key)
        daily = await _qweather_3d(client, loc["id"], key) if days >= 1 else []
    return _format_qweather(loc, now, daily, days)


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
    """并发竞速：QWeather 主 + wttr.in 备，谁先成功用谁。"""
    days = max(0, min(days, 2))

    async def try_qweather() -> dict:
        return await _qweather_weather(location, days)

    async def try_wttr() -> dict:
        return await _wttr_weather_entry(location, days)

    tasks = [
        asyncio.create_task(try_qweather(), name="qweather"),
        asyncio.create_task(try_wttr(), name="wttr"),
    ]
    last_error: str | None = None
    try:
        done, pending = await asyncio.wait(tasks, timeout=_OVERALL_TIMEOUT, return_when=asyncio.FIRST_COMPLETED)
    except Exception as e:
        last_error = f"wait failed: {e}"
        done, pending = set(), tasks

    for t in done:
        try:
            result = t.result()
            if result and not result.get("error"):
                for p in pending:
                    p.cancel()
                return result
            err = (result or {}).get("error", {})
            last_error = f"{t.get_name()}: {err.get('code', '?')} {err.get('message', err)}"
        except Exception as e:
            last_error = f"{t.get_name()}: {type(e).__name__}: {e}"

    for t in tasks:
        if not t.done():
            t.cancel()

    if last_error is None:
        last_error = f"双源均超时（>{_OVERALL_TIMEOUT}s）"
    return {
        "error": {
            "code": "upstream_unavailable",
            "message": f"天气服务暂时不可达：{last_error}",
            "timeout_s": _OVERALL_TIMEOUT,
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

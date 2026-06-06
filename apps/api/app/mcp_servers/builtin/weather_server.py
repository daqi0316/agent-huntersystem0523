"""mcp-weather server — 薄壳包 WeatherSkill（v0.3 §3.1 pilot B 轨道）。

外部依赖：QWeather / wttr.in / Tavily 三级 fallback。
无 QWEATHER_API_KEY 时函数返 error，但 server 启动通路验证 OK。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.mcp_servers._base import entrypoint
from app.skills.weather.skill import skill as weather_skill


@entrypoint("mcp-weather", capability="read", version="1.0.0")
def main():
    return weather_skill.get_tools(), weather_skill.get_handlers()


if __name__ == "__main__":
    main()

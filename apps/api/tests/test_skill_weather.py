from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestGetWeather:
    @patch("app.skills.weather.skill.httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
        from app.skills.weather.skill import _get_weather

        mock_qw = AsyncMock(return_value={"error": {"code": "mock"}})
        with patch("app.skills.weather.skill._qweather_weather", mock_qw):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            mock_resp = Mock()
            mock_resp.json.return_value = {
                "current_condition": [
                    {
                        "temp_C": "22",
                        "FeelsLikeC": "20",
                        "humidity": "65",
                        "windspeedKmph": "15",
                        "winddir16Point": "NNE",
                        "weatherDesc": [{"value": "Partly cloudy"}],
                        "visibility": "10",
                        "pressure": "1015",
                    }
                ]
            }
            mock_client.get.return_value = mock_resp

            result = await _get_weather("Beijing")
            assert result["location"] == "Beijing"
            assert result["current"]["temp_c"] == "22"
            assert result["current"]["desc"] == "Partly cloudy"

    @patch("app.skills.weather.skill.httpx.AsyncClient")
    async def test_missing_current_condition(self, mock_client_cls):
        from app.skills.weather.skill import _get_weather

        mock_qw = AsyncMock(return_value={"error": {"code": "mock"}})
        with patch("app.skills.weather.skill._qweather_weather", mock_qw):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_resp = Mock()
            mock_resp.json.return_value = {}
            mock_client.get.return_value = mock_resp

            result = await _get_weather("Nowhere")
            assert result["current"]["temp_c"] is None

    @patch("app.skills.weather.skill.httpx.AsyncClient")
    async def test_http_error(self, mock_client_cls):
        from app.skills.weather.skill import _get_weather

        mock_qw = AsyncMock(return_value={"error": {"code": "mock"}})
        mock_ws = AsyncMock(return_value={"error": {"code": "mock"}})
        with patch("app.skills.weather.skill._qweather_weather", mock_qw), \
             patch("app.skills.weather.skill._web_search_weather", mock_ws):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = Exception("connection failed")

            result = await _get_weather("BadCity")
            assert "error" in result


class TestWeatherSkill:
    def test_name(self):
        from app.skills.weather.skill import WeatherSkill
        assert WeatherSkill().name == "weather"

    def test_description(self):
        from app.skills.weather.skill import WeatherSkill
        assert "天气" in WeatherSkill().description

    def test_get_tools(self):
        from app.skills.weather.skill import WeatherSkill
        tools = WeatherSkill().get_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "get_weather"

    def test_get_handlers(self):
        from app.skills.weather.skill import WeatherSkill
        handlers = WeatherSkill().get_handlers()
        assert "get_weather" in handlers

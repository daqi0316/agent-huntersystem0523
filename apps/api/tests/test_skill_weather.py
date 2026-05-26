from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.skills.weather.skill import WeatherSkill, _get_weather


class TestGetWeather:
    @patch("app.skills.weather.skill.httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
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
        assert result["temp_c"] == "22"
        assert result["weather_desc"] == "Partly cloudy"

    @patch("app.skills.weather.skill.httpx.AsyncClient")
    async def test_missing_current_condition(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_client.get.return_value = mock_resp

        result = await _get_weather("Nowhere")
        assert result["temp_c"] == "N/A"

    @patch("app.skills.weather.skill.httpx.AsyncClient")
    async def test_http_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("connection failed")

        with pytest.raises(Exception):
            await _get_weather("BadCity")


class TestWeatherSkill:
    def test_name(self):
        assert WeatherSkill().name == "weather"

    def test_description(self):
        assert "天气" in WeatherSkill().description

    def test_get_tools(self):
        tools = WeatherSkill().get_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "get_weather"

    def test_get_handlers(self):
        handlers = WeatherSkill().get_handlers()
        assert "get_weather" in handlers

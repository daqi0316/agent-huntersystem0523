"""JDGeneratorService tests — mocked GenEvalLoop."""

from unittest.mock import AsyncMock, patch

import pytest


class TestJDGeneratorService:
    """Tests for JDGeneratorService."""

    @pytest.fixture
    def service(self):
        from app.services.jd_generator import JDGeneratorService

        return JDGeneratorService()

    def test_init_creates_gen_eval_loop(self, service):
        """Constructor creates GenEvalLoop with correct settings."""
        assert service.agent is not None
        assert service.agent.name == "jd_generator"

    @pytest.mark.asyncio
    async def test_generate_jd_with_auto_improve(self, service):
        """generate_jd with auto_improve=True delegates to agent.run."""
        mock_result = {
            "agent": "jd_generator",
            "status": "completed",
            "final_output": "# Senior Engineer JD\n\n## Overview\n...",
            "iterations": [{"iteration": 1, "generated": "...", "passed": True}],
            "total_iterations": 1,
            "passed": True,
            "threshold": 7.0,
        }
        service.agent.run = AsyncMock(return_value=mock_result)

        result = await service.generate_jd(
            title="Senior Engineer",
            requirements="Python, 5 years",
            preferences="Remote OK",
            auto_improve=True,
        )

        service.agent.run.assert_awaited_once_with({
            "title": "Senior Engineer",
            "requirements": "Python, 5 years",
            "preferences": "Remote OK",
        })
        assert result["status"] == "completed"
        assert result["agent"] == "jd_generator"
        assert "final_output" in result

    @pytest.mark.asyncio
    async def test_generate_jd_without_auto_improve(self, service):
        """generate_jd with auto_improve=False does single generation."""
        mock_output = "# Junior Dev JD\n\nSingle pass output"
        service.agent.generate = AsyncMock(return_value=mock_output)

        result = await service.generate_jd(
            title="Junior Dev",
            requirements="Entry level",
            auto_improve=False,
        )

        service.agent.generate.assert_awaited_once()
        assert result["status"] == "completed"
        assert result["final_output"] == mock_output
        assert result["total_iterations"] == 1
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_generate_jd_minimal_args(self, service):
        """generate_jd works with only title and requirements."""
        mock_result = {
            "agent": "jd_generator",
            "status": "completed",
            "final_output": "# JD\n\nContent",
            "iterations": [],
            "total_iterations": 1,
            "passed": True,
            "threshold": 7.0,
        }
        service.agent.run = AsyncMock(return_value=mock_result)

        result = await service.generate_jd(
            title="Title",
            requirements="Req",
        )

        assert result["agent"] == "jd_generator"
        service.agent.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_improve_jd(self, service):
        """improve_jd calls agent.generate with feedback."""
        mock_improved = "# Improved JD\n\nBased on feedback..."
        service.agent.generate = AsyncMock(return_value=mock_improved)

        result = await service.improve_jd(
            jd_content="# Original JD",
            feedback="Add more details",
        )

        service.agent.generate.assert_awaited_once()
        assert result["jd_content"] == mock_improved
        assert result["original"] == "# Original JD"
        assert result["feedback"] == "Add more details"

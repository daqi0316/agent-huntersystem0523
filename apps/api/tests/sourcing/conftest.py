"""pytest fixtures for sourcing tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_llm_client():
    """Create a mock LLMClient that returns fixed JSON responses."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def sample_candidate():
    """Minimal candidate dict for unit tests."""
    return {
        "name": "张三",
        "current_title": "Python高级工程师",
        "current_company": "字节跳动",
        "location": "北京",
        "salary": "35K-50K",
        "experience_years": 5,
        "education": "本科",
        "skills": ["python", "django", "docker"],
        "summary": "5年后端开发经验",
        "raw_data": {
            "boss_zhipin": {
                "gender": "男",
                "age": 28,
                "degree": "本科",
            }
        },
    }


@pytest.fixture
def sample_candidate_minimal():
    """Minimal candidate with only required fields."""
    return {
        "name": "李四",
        "skills": ["java"],
    }


@pytest.fixture
def sample_jd_text():
    return (
        "我们正在寻找一位资深Python后端工程师，"
        "负责高并发微服务架构设计与开发。"
        "要求5年以上Python开发经验，熟悉Django/Flask框架，"
        "有分布式系统设计和开发经验，熟悉MySQL/Redis等中间件。"
    )


@pytest.fixture
def sample_jd_requirements():
    return (
        "1. 5年以上Python开发经验\n"
        "2. 熟悉Django、Flask等Web框架\n"
        "3. 熟悉MySQL、Redis、消息队列\n"
        "4. 有高并发系统设计经验\n"
        "5. 良好的团队协作能力"
    )

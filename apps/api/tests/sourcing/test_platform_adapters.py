"""Tests for platform adapter parsing logic (parse_list / parse_detail / _extract_card)"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sourcing.platforms.github import GitHubAdapter
from app.sourcing.platforms.liepin import LiepinAdapter
from app.sourcing.platforms.linkedin import LinkedInAdapter
from app.sourcing.platforms.maimai import MaimaiAdapter


# ════════════════════════════════════════════════
# LiepinAdapter
# ════════════════════════════════════════════════

class TestLiepinAdapter:
    @pytest.fixture
    def adapter(self):
        return LiepinAdapter(config={})

    def test_name_and_category(self):
        assert LiepinAdapter.name == "liepin"
        assert LiepinAdapter.display_name == "猎聘"
        assert LiepinAdapter.category == "job_board"
        assert LiepinAdapter.anti_crawl_level == 3

    def test_text_found(self, adapter):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup('<div class="name">张三</div>', "html.parser")
        result = adapter._text(soup, ".name")
        assert result == "张三"

    def test_text_not_found(self, adapter):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div></div>", "html.parser")
        result = adapter._text(soup, ".nonexistent")
        assert result is None

    def test_text_exception_returns_none(self, adapter):
        """Passing None or invalid object should return None."""
        result = adapter._text(None, ".name")
        assert result is None

    async def test_parse_list_empty_html(self, adapter):
        result = await adapter.parse_list("<html></html>")
        assert result == []

    async def test_parse_list_with_cards(self, adapter):
        html = """
        <div class="job-list-item">
            <div class="name">张三</div>
            <div class="title">Python工程师</div>
            <div class="salary">30K-50K</div>
            <div class="company">字节跳动</div>
            <div class="tag">python</div>
            <div class="tag">django</div>
            <a href="/resume/12345">查看</a>
        </div>
        <div class="job-list-item">
            <div class="name">李四</div>
            <div class="title">Java架构师</div>
            <a href="https://example.com/resume/67890">查看</a>
        </div>
        """
        result = await adapter.parse_list(html)
        assert len(result) == 2
        assert result[0]["name"] == "张三"
        assert result[0]["title"] == "Python工程师"
        assert result[0]["salary"] == "30K-50K"
        assert result[0]["company"] == "字节跳动"
        assert "python" in result[0]["tags"]
        assert "django" in result[0]["tags"]
        assert result[0]["url"] == "https://www.liepin.com/resume/12345"
        assert result[1]["name"] == "李四"
        assert result[1]["url"] == "https://example.com/resume/67890"

    async def test_parse_list_skips_empty_cards(self, adapter):
        html = """<div class="job-list-item"></div>"""
        result = await adapter.parse_list(html)
        assert result == []

    async def test_parse_detail_with_all_sections(self, adapter):
        html = """
        <html>
            <h1>张三</h1>
            <div class="title">Python工程师</div>
            <div class="salary">30K-50K</div>
            <div class="company-name">字节跳动</div>
            <div class="skill-tag">python</div>
            <div class="skill-tag">django</div>
            <div class="work-experience">
                <li>2020-2023 字节跳动 后端开发</li>
            </div>
            <div class="education">本科</div>
            <div class="personal-desc">5年后端开发经验</div>
        </html>
        """
        result = await adapter.parse_detail(html)
        assert result["name"] == "张三"
        assert result["title"] == "Python工程师"
        assert result["skills"] == ["python", "django"]
        assert len(result["experiences"]) == 1
        assert result["education"] == "本科"
        assert result["description"] is not None
        assert result["platform"] == "liepin"

    async def test_parse_detail_minimal(self, adapter):
        result = await adapter.parse_detail("<html></html>")
        assert result["name"] is None
        assert result["skills"] == []


# ════════════════════════════════════════════════
# MaimaiAdapter
# ════════════════════════════════════════════════

class TestMaimaiAdapter:
    @pytest.fixture
    def adapter(self):
        return MaimaiAdapter(config={})

    def test_name_and_category(self):
        assert MaimaiAdapter.name == "maimai"
        assert MaimaiAdapter.display_name == "脉脉"
        assert MaimaiAdapter.category == "social"
        assert MaimaiAdapter.requires_login is True

    def test_parse_search_item_with_profile(self, adapter):
        item = {
            "profile": {
                "name": "张三",
                "title": "Python工程师",
                "company": "字节跳动",
                "city": "北京",
                "skills": ["python", "django"],
                "education": "本科",
                "id": "12345",
            },
            "desc": "5年后端经验",
        }
        result = adapter._parse_search_item(item)
        assert result["name"] == "张三"
        assert result["title"] == "Python工程师"
        assert result["company"] == "字节跳动"
        assert result["location"] == "北京"
        assert result["skills"] == ["python", "django"]
        assert result["education"] == "本科"
        assert result["url"] == "https://maimai.cn/profile/12345"
        assert result["platform"] == "maimai"

    def test_parse_search_item_with_user_dict(self, adapter):
        item = {
            "user": {"name": "李四", "title": "Java架构师"},
            "company": "阿里",
            "city": "杭州",
        }
        result = adapter._parse_search_item(item)
        assert result["name"] == "李四"
        assert result["title"] == "Java架构师"
        assert result["company"] == "阿里"

    def test_parse_search_item_minimal(self, adapter):
        result = adapter._parse_search_item({"name": "王五"})
        assert result["name"] == "王五"

    async def test_parse_list_empty(self, adapter):
        result = await adapter.parse_list("<html></html>")
        assert result == []

    async def test_parse_list_with_cards(self, adapter):
        html = """
        <div class="user-card">
            <div class="name">张三</div>
            <div class="title">工程师</div>
            <div class="company">字节跳动</div>
        </div>
        """
        result = await adapter.parse_list(html)
        assert len(result) == 1
        assert result[0]["name"] == "张三"

    async def test_parse_detail(self, adapter):
        html = """
        <html>
            <h1>张三</h1>
            <div class="title">工程师</div>
            <div class="company">字节跳动</div>
            <div class="skill-tag">python</div>
        </html>
        """
        result = await adapter.parse_detail(html)
        assert result["name"] == "张三"
        assert "python" in result["skills"]
        assert result["platform"] == "maimai"


# ════════════════════════════════════════════════
# LinkedInAdapter
# ════════════════════════════════════════════════

class TestLinkedInAdapter:
    @pytest.fixture
    def adapter(self):
        return LinkedInAdapter(config={})

    def test_name_and_category(self):
        assert LinkedInAdapter.name == "linkedin"
        assert LinkedInAdapter.display_name == "LinkedIn"
        assert LinkedInAdapter.category == "social"
        assert LinkedInAdapter.anti_crawl_level == 2

    def test_text_found(self, adapter):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup('<a class="actor-name">John Doe</a>', "html.parser")
        result = adapter._text(soup, ".actor-name")
        assert result == "John Doe"

    async def test_parse_list_empty(self, adapter):
        result = await adapter.parse_list("<html></html>")
        assert result == []

    async def test_parse_list_with_cards(self, adapter):
        html = """
        <div class="reusable-search__result-container">
            <div class="entity-result__title-text"><a href="/in/johndoe/">John Doe</a></div>
            <div class="entity-result__primary-subtitle">Software Engineer</div>
            <div class="entity-result__secondary-subtitle">Google</div>
            <div class="entity-result__summary">San Francisco</div>
        </div>
        <div class="reusable-search__result-container">
            <div class="entity-result__title-text"><a href="https://linkedin.com/in/janedoe/">Jane Doe</a></div>
            <div class="entity-result__primary-subtitle">Product Manager</div>
        </div>
        """
        result = await adapter.parse_list(html)
        assert len(result) == 2
        assert result[0]["name"] == "John Doe"
        assert result[0]["title"] == "Software Engineer"
        assert result[0]["company"] == "Google"
        assert result[0]["location"] == "San Francisco"
        assert "linkedin.com/in/johndoe" in result[0]["url"]
        assert result[1]["name"] == "Jane Doe"
        assert result[1]["company"] == ""

    async def test_parse_list_skips_empty_cards(self, adapter):
        html = """<div class="reusable-search__result-container"></div>"""
        result = await adapter.parse_list(html)
        assert result == []

    async def test_parse_detail(self, adapter):
        html = """
        <html>
            <h1>John Doe</h1>
            <div class="top-card-layout__headline">Software Engineer at Google</div>
            <div class="top-card-layout__first-subline">San Francisco</div>
            <div class="about-section">Experienced software engineer</div>
            <div class="skills-section">
                <li>Python</li>
                <li>JavaScript</li>
            </div>
            <div class="experience-section">
                <li>Google 2020-present</li>
            </div>
            <div class="education-section">MIT</div>
        </html>
        """
        result = await adapter.parse_detail(html)
        assert result["name"] == "John Doe"
        assert result["title"] == "Software Engineer at Google"
        assert result["location"] == "San Francisco"
        assert result["description"] == "Experienced software engineer"
        assert "Python" in result["skills"]
        assert len(result["experiences"]) == 1
        assert result["education"] == "MIT"


# ════════════════════════════════════════════════
# GitHubAdapter
# ════════════════════════════════════════════════

class TestGitHubAdapter:
    @pytest.fixture
    def adapter(self):
        return GitHubAdapter(config={})

    def test_name_and_category(self):
        assert GitHubAdapter.name == "github"
        assert GitHubAdapter.display_name == "GitHub"
        assert GitHubAdapter.category == "code"
        assert GitHubAdapter.anti_crawl_level == 1

    def test_headers_without_token(self, adapter):
        headers = adapter._headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github.v3+json"

    def test_headers_with_token(self, adapter):
        adapter._token = "ghp_test123"
        headers = adapter._headers()
        assert headers["Authorization"] == "Bearer ghp_test123"

    def test_load_token_from_config(self):
        adapter = GitHubAdapter(config={"github_token": "from_config"})
        assert adapter._token == "from_config"

    async def test_parse_list_returns_empty_with_warning(self, adapter):
        result = await adapter.parse_list("<html></html>")
        assert result == []

    async def test_parse_detail_returns_empty(self, adapter):
        result = await adapter.parse_detail("<html></html>")
        assert result == {}

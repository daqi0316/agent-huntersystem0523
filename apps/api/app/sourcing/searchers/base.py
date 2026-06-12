"""
候选人搜索器抽象层 — 工程化、模块化、可扩展。

每个平台（LinkedIn / 猎聘 / Boss / 脉脉）实现一个 CandidateSearcher，
统一的 CandidateProfile + CandidateSearchResult 数据模型。

搜索策略等级:
  Level 1: 平台原生候选人数据库（需企业认证账号 + 登录态）
  Level 2: 平台公开个人主页（搜索引擎可索引，如 LinkedIn /in/ 页面）
  Level 3: 跨平台候选人信息聚合（通用搜索兜底）

各平台当前能力:
  - linkedin: Level 2 ✅ — 公开 profile 页面可搜索
  - liepin:   Level 1 （需猎聘企业账号登录后才能搜索候选人简历）
  - boss_zhipin: Level 1 （需 Boss 企业账号登录）
  - maimai:   Level 1 （需脉脉企业账号登录）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── 数据模型 ──


@dataclass
class CandidateProfile:
    """统一候选人数据结构"""

    name: str
    title: str | None = None  # 当前/最近职位
    company: str | None = None  # 当前/最近公司
    location: str | None = None
    profile_url: str = ""
    platform: str = ""  # "linkedin" | "liepin" | ...
    source: str = ""  # "public_profile" | "job_listing" | "platform_adapter"
    skills: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    summary: str | None = None
    photo_url: str | None = None


@dataclass
class CandidateSearchResult:
    """候选人搜索结果"""

    success: bool
    candidates: list[CandidateProfile] = field(default_factory=list)
    platform: str = ""
    search_type: str = ""  # "public_profile" | "authenticated" | "job_listing" | "general_web"
    error_message: str | None = None
    total_found: int = 0


# ── 搜索器抽象基类 ──


class CandidateSearcher(ABC):
    """平台候选人搜索器基类。

    子类只需实现 search() 方法。注册由 @register_searcher 装饰器或 registry 自动完成。
    """

    # 子类覆写
    platform: str = ""  # 唯一标识，如 "linkedin"
    display_name: str = ""  # 展示名
    search_type: str = ""  # "public_profile" | "authenticated" | "job_listing"
    requires_auth: bool = False  # 是否需要平台登录才能搜候选人
    supported: bool = True  # 当前是否可用

    @abstractmethod
    async def search(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        """搜索候选人。返回统一格式的结果。"""
        ...

    def describe_capability(self) -> str:
        """描述此搜索器的能力（用于 tool description / system prompt）。"""
        if self.search_type == "public_profile":
            return (
                f"{self.display_name}：可搜索公开个人主页（如 linkedin.com/in/ 页面），"
                f"返回真实候选人个人资料。无需平台登录。"
            )
        elif self.search_type == "authenticated":
            return (
                f"{self.display_name}：候选人简历/人才库搜索需要企业账号登录。"
                f"当前返回该平台公开可访问的招聘信息作为参考。"
            )
        elif self.search_type == "job_listing":
            return f"{self.display_name}：返回该平台上的公开招聘岗位信息（职位/JD），非候选人简历。"
        return f"{self.display_name}：搜索结果来自 {self.search_type}。"


def _tavily_search(
    query: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    include_answer: bool = True,
) -> dict[str, Any]:
    """Tavily 统一查询封装。

    所有继承自 CandidateSearcher 的子类都应使用此函数进行 Tavily 查询，
    避免重复的 API Key 检查 / 错误处理逻辑。
    """
    import os

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return {
            "success": False,
            "error_message": "TAVILY_API_KEY 未配置，无法进行互联网搜索",
        }

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        kwargs: dict[str, Any] = dict(
            query=query,
            max_results=max_results,
            include_answer=include_answer,
            include_raw_content=False,
        )
        if include_domains:
            kwargs["search_depth"] = "advanced"
            kwargs["include_domains"] = include_domains

        result = client.search(**kwargs)
        return {
            "success": True,
            "sources": result.get("results", []),
            "answer": result.get("answer", ""),
        }
    except ImportError:
        return {"success": False, "error_message": "Tavily 包未安装，请 pip install tavily"}
    except Exception as e:
        logger.exception("Tavily search failed: %s", e)
        return {"success": False, "error_message": str(e)}


def tavily_to_candidates(
    sources: list[dict[str, Any]],
    platform: str,
    source_tag: str,
    extract_name: bool = True,
) -> list[CandidateProfile]:
    """将 Tavily 搜索结果转换为 CandidateProfile 列表。

    通用转换逻辑，各平台搜索器可以覆盖 extract_name / extract_title 等逻辑。
    """
    candidates: list[CandidateProfile] = []
    for s in sources:
        title = s.get("title", "")
        url = s.get("url", "")
        content = s.get("content", "")

        # 尝试从 title/content 提取候选人姓名
        name = title.split(" - ")[0].strip() if extract_name and " - " in title else title[:40]

        candidates.append(
            CandidateProfile(
                name=name,
                title=title[:120],
                profile_url=url,
                platform=platform,
                source=source_tag,
                summary=content[:300] if content else None,
            )
        )
    return candidates

"""
通用互联网候选人搜索 — 最终兜底。

不限定平台域名，通过 Tavily 在互联网上搜索公开的候选人信息。
可用于搜索任何平台+个人简历/主页的组合。
"""

from __future__ import annotations

import logging

from app.sourcing.searchers.base import (
    CandidateSearcher,
    CandidateSearchResult,
    CandidateProfile,
    _tavily_search,
    tavily_to_candidates,
)

logger = logging.getLogger(__name__)


class WebSearchFallback(CandidateSearcher):
    platform = "web"
    display_name = "互联网"
    search_type = "general_web"
    requires_auth = False
    supported = True

    async def search(
        self,
        keywords: str,
        location: str = "",
        max_results: int = 5,
    ) -> CandidateSearchResult:
        query = keywords.strip()
        if location:
            query = f"{query} {location}"
        query = f"{query} 简历 候选人"

        tavily_result = _tavily_search(
            query=query,
            max_results=max_results,
            include_answer=True,
        )

        if not tavily_result["success"]:
            return CandidateSearchResult(
                success=False,
                platform=self.platform,
                search_type=self.search_type,
                error_message=tavily_result.get("error_message", "搜索失败"),
            )

        sources = tavily_result.get("sources", [])
        candidates = tavily_to_candidates(
            sources, platform=self.platform, source_tag="general_web"
        )

        return CandidateSearchResult(
            success=True,
            candidates=candidates,
            platform=self.platform,
            search_type=self.search_type,
            total_found=len(candidates),
        )

    def describe_capability(self) -> str:
        return "互联网：在公开互联网上搜索候选人相关信息，不限平台。"

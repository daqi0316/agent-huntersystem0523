"""
脉脉候选人搜索器。

能力: Level 1（需企业认证）
脉脉的人才搜索功能同样需要企业账号或会员权限。
公开可搜索的只有文章/动态，非候选人简历。
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


class MaimaiSearcher(CandidateSearcher):
    platform = "maimai"
    display_name = "脉脉"
    search_type = "authenticated"
    requires_auth = True
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
        query = f"{query} 脉脉"

        tavily_result = _tavily_search(
            query=query,
            max_results=max_results,
            include_domains=["maimai.cn"],
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
            sources, platform=self.platform, source_tag="job_listing"
        )

        return CandidateSearchResult(
            success=True,
            candidates=candidates,
            platform=self.platform,
            search_type=self.search_type,
            total_found=len(candidates),
        )

    def describe_capability(self) -> str:
        return (
            "脉脉：候选人搜索需要企业账号或会员权限。"
            "当前返回脉脉平台上的公开内容，并非候选人简历。"
        )

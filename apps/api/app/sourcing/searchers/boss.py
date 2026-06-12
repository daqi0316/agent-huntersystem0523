"""
Boss直聘候选人搜索器。

能力: Level 1（需企业认证）
与猎聘类似，Boss直聘的人才简历库需要企业账号登录后才能访问。
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


class BossZhipinSearcher(CandidateSearcher):
    platform = "boss_zhipin"
    display_name = "Boss直聘"
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
        query = f"{query} Boss直聘"

        tavily_result = _tavily_search(
            query=query,
            max_results=max_results,
            include_domains=["zhipin.com"],
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
            "Boss直聘：候选人简历搜索需要企业账号登录。"
            "当前返回 Boss直聘上的公开招聘岗位信息（JD）作为参考，并非候选人简历。"
        )

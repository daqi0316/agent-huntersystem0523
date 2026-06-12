"""
search_platform — 在外部招聘平台搜索候选人简历。

搜索策略（按优先级）:
  1. 平台专用搜索器（当前可用: LinkedIn 公开个人主页）
  2. 通用互联网搜索（跨平台兜底）

各平台候选人搜索能力:
  - linkedin: 可搜索公开个人主页（linkedin.com/in/），无需登录 ✅
  - github:   可搜索 GitHub 公开个人主页，适合技术岗位 ✅
  - liepin:   已配置企业账号时可浏览器自动登录搜索真实候选人简历（需设置 LIEPIN_USERNAME + LIEPIN_PASSWORD）
  - boss_zhipin: 候选人才库需企业账号登录，当前返回 JD 参考信息
  - maimai:   同上

设计: 搜索逻辑委托给 app/sourcing/searchers/ 模块，
       每个平台实现独立的 CandidateSearcher。
"""

from __future__ import annotations

import logging

from app.sourcing.searchers.registry import get_searcher
from app.sourcing.tools.base import SourcingTool, error_result, success_result

logger = logging.getLogger(__name__)

# ── Tool Schema ──

_TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "search_platform",
        "description": (
            "在外部招聘平台搜索候选人简历/资料。"
            "可指定搜索关键词、平台、地点。\n\n"
             "各平台能力说明:\n"
             "  - linkedin（推荐）: 搜索公开个人主页（linkedin.com/in/），"
             "可获取真实候选人姓名、职位、公司。无需登录。\n"
             "  - github（推荐）: 搜索 GitHub 公开个人主页，"
             "可获取开发者姓名、bio、位置、公司、技术栈。适合技术岗位。无需登录。\n"
             "  - liepin: 工具内部使用 Playwright 浏览器自动化完成登录，"
             "已配置企业账号时可直接搜索真实候选人简历。你不需要手动登录。\n"
             "  - boss_zhipin / maimai: 候选人才库需要企业账号登录，"
             "当前返回平台上的公开招聘信息作为参考。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "搜索关键词，如岗位名称、技能、公司名组合（如「CTO 人工智能 北京」）。",
                },
                "platform": {
                    "type": "string",
                    "enum": ["linkedin", "github", "liepin", "boss_zhipin", "maimai", "web"],
                    "description": (
                        "目标招聘平台。\n"
                        "  - linkedin（推荐）: 搜索公开个人主页，返回真实候选人简历\n"
                        "  - github（推荐）: 搜索 GitHub 公开个人主页，适合技术岗位\n"
                         "  - liepin: 猎聘网。工具内部用 Playwright 自动登录，"
                         "你不需要手动登录。配置企业账号后可直接搜索真实候选人简历。\n"
                        "  - boss_zhipin: Boss直聘（候选人信息需企业账号登录）\n"
                        "  - maimai: 脉脉（候选人信息需企业账号登录）\n"
                        "  - web: 通用互联网搜索（不限平台）"
                    ),
                },
                "location": {
                    "type": "string",
                    "description": "工作地点（可选，如「北京」「上海」「远程」）。",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数（默认 5，最大 15）。",
                    "default": 5,
                },
            },
            "required": ["keywords", "platform"],
        },
    },
}

# 平台名 → 显示名映射
PLATFORM_DISPLAY: dict[str, str] = {
    "web": "互联网",
    "linkedin": "LinkedIn",
    "github": "GitHub",
    "liepin": "猎聘",
    "boss_zhipin": "Boss直聘",
    "maimai": "脉脉",
}


class PlatformSearchTool(SourcingTool):
    """多平台候选人搜索工具 — 委托各平台 CandidateSearcher 执行。"""

    @property
    def tool_schema(self) -> dict:
        return _TOOL_SCHEMA

    async def execute(
        self,
        keywords: str = "",
        platform: str = "web",
        location: str = "",
        max_results: int = 5,
        **kwargs,
    ) -> dict:
        if not keywords.strip():
            return error_result("搜索关键词不能为空")

        max_results = min(max_results, 15)
        display = PLATFORM_DISPLAY.get(platform, platform)

        # Step 1: 找平台专属搜索器
        searcher = get_searcher(platform)

        if searcher is None or not searcher.supported:
            # 未注册的平台 → 通用搜索
            return await self._web_fallback(keywords, location, max_results, platform, display)

        # Step 2: 执行平台搜索
        result = await searcher.search(
            keywords=keywords,
            location=location,
            max_results=max_results,
        )

        if result.success and result.candidates:
            items = []
            for c in result.candidates:
                items.append({
                    "title": c.name,
                    "url": c.profile_url,
                    "content": c.summary or c.title or "",
                    "platform": platform,
                })

            return success_result(
                items,
                summary=self._format_summary(platform, display, result),
                platform=platform,
            )

        # Step 3: 平台搜索无结果 → 通用搜索兜底
        logger.info(
            "Searcher for %s returned %d candidates, falling back to web",
            platform, len(result.candidates),
        )
        return await self._web_fallback(keywords, location, max_results, platform, display)

    async def _web_fallback(
        self,
        keywords: str,
        location: str,
        max_results: int,
        platform: str,
        display: str,
    ) -> dict:
        """通用互联网搜索兜底"""
        from app.sourcing.searchers.web import WebSearchFallback

        fallback = WebSearchFallback()
        result = await fallback.search(
            keywords=f"{keywords} {display}",
            location=location,
            max_results=max_results,
        )

        if not result.success or not result.candidates:
            return error_result(
                result.error_message or f"在 {display} 未找到相关结果",
                platform=platform,
            )

        items = []
        for c in result.candidates:
            items.append({
                "title": c.name,
                "url": c.profile_url,
                "content": c.summary or c.title or "",
                "platform": platform,
            })

        return success_result(
            items,
            summary=f"在互联网上找到 {len(items)} 条相关结果（{display}暂无候选人数据）",
            platform=platform,
        )

    @staticmethod
    def _format_summary(platform: str, display: str, result) -> str:
        """根据搜索类型和结果来源生成合适的摘要"""
        search_type = result.search_type
        count = result.total_found

        # 检查是否有真实的平台适配器搜索结果（浏览器登录成功）
        has_real_candidates = any(
            c.source == "platform_adapter" for c in result.candidates
        ) if result.candidates else False

        if has_real_candidates:
            return f"在 {display} 找到 {count} 个候选人（企业账号登录搜索）"
        elif search_type == "public_profile":
            return f"在 {display} 找到 {count} 个公开个人主页"
        elif search_type == "authenticated":
            return (
                f"在 {display} 找到 {count} 条参考信息。"
                f"注意：{display}候选人简历需企业账号登录后搜索，当前结果为公开可访问的招聘信息。"
            )
        return f"在 {display} 找到 {count} 条相关结果"


# ── 单例 ──

platform_search_tool = PlatformSearchTool()

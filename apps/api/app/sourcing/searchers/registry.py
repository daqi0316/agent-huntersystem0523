"""
搜索器注册中心 — pkgutil 自动发现 + 路由。

用法:
  get_searcher("linkedin")       → LinkedInSearcher 实例
  get_searcher("liepin")         → LiepinSearcher 实例
  list_searchers()               → 所有注册的搜索器信息
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from typing import Any

from app.sourcing.searchers.base import CandidateSearcher, CandidateSearchResult

logger = logging.getLogger(__name__)

_SEARCHERS: dict[str, type[CandidateSearcher]] = {}


def discover_searchers():
    """自动扫描 searchers/ 目录注册所有 CandidateSearcher 子类"""
    pkg_path = os.path.dirname(__file__)
    for _, name, _ in pkgutil.iter_modules([pkg_path]):
        if name.startswith("_") or name in ("base", "registry"):
            continue
        try:
            module = importlib.import_module(f".{name}", __package__)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, CandidateSearcher)
                    and attr is not CandidateSearcher
                    and getattr(attr, "platform", "")
                ):
                    _SEARCHERS[attr.platform] = attr
                    logger.debug("Discovered searcher: %s (%s)", attr.platform, attr.display_name)
        except Exception as e:
            logger.warning("Failed to load searcher %s: %s", name, e)


def get_searcher(platform: str) -> CandidateSearcher | None:
    """获取平台对应的搜索器实例。未找到返回 None。"""
    cls = _SEARCHERS.get(platform)
    if cls is None:
        return None
    return cls()


def search_candidates(
    platform: str,
    keywords: str,
    location: str = "",
    max_results: int = 5,
) -> CandidateSearchResult:
    """统一的候选人搜索入口：路由到对应平台搜索器。

    如果平台未注册，返回 error 结果。
    """
    searcher = get_searcher(platform)
    if searcher is None:
        return CandidateSearchResult(
            success=False,
            platform=platform,
            error_message=f"未支持的平台: {platform}，可用平台: {list(_SEARCHERS.keys())}",
        )
    return searcher.search(keywords, location, max_results)


def list_searchers() -> list[dict[str, Any]]:
    """列出所有注册的搜索器及其能力描述"""
    return [
        {
            "platform": cls.platform,
            "display_name": cls.display_name,
            "search_type": cls.search_type,
            "requires_auth": cls.requires_auth,
            "capability": cls().describe_capability(),
        }
        for cls in _SEARCHERS.values()
    ]


# 模块导入时自动发现
discover_searchers()

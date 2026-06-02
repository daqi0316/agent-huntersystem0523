"""Prompt 缓存管理器 — 带 mtime + size 失效的版本化缓存。

提供:
- PromptCacheManager: 线程安全的 .md 文件读取缓存
- cached_read: 模块级便利函数（使用单例）
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """单条缓存记录 — 包含内容 + 文件指纹（mtime + size + version）。"""

    content: str
    mtime: float
    size: int
    version: int


class PromptCacheManager:
    """线程安全的 Prompt 文件缓存。

    失效策略：mtime + size 任一变化即重新读取。
    并发：threading.Lock 保护 _cache 字典读写。
    边界：FileNotFoundError 返回空串（不抛），记录 warning。
    """

    def __init__(self) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._version = 0

    def get(self, key: str, path: Path) -> str:
        """读取指定 key 对应文件，命中缓存则直接返回。

        Args:
            key: 缓存键（通常是 "SOUL" / "MEMORY" / "user:42" 等）
            path: .md 文件绝对路径

        Returns:
            文件内容字符串。文件不存在返回 ""。
        """
        with self._lock:
            try:
                stat = path.stat()
            except FileNotFoundError:
                logger.warning("Prompt file not found: %s (key=%s)", path, key)
                # 文件不存在 → 清除可能存在的陈旧缓存
                self._cache.pop(key, None)
                return ""

            entry = self._cache.get(key)
            if entry and entry.mtime == stat.st_mtime and entry.size == stat.st_size:
                return entry.content

            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError as e:
                logger.error("Encoding error reading %s: %s", path, e)
                raise

            self._cache[key] = CacheEntry(
                content=content,
                mtime=stat.st_mtime,
                size=stat.st_size,
                version=self._version,
            )
            logger.debug("Cached prompt '%s' (%d chars, version=%d)", key, len(content), self._version)
            return content

    def invalidate(self, key: str | None = None) -> None:
        """清除缓存。

        Args:
            key: 指定 key 清除单条；None 清除全部并 bump version。
        """
        with self._lock:
            if key is None:
                cleared = len(self._cache)
                self._cache.clear()
                self._version += 1
                logger.info("Prompt cache fully invalidated (%d entries cleared, version=%d)", cleared, self._version)
            else:
                removed = self._cache.pop(key, None)
                if removed:
                    logger.debug("Invalidated cache key '%s'", key)

    def stats(self) -> dict:
        """返回缓存统计（调试用）。"""
        with self._lock:
            return {
                "entries": len(self._cache),
                "version": self._version,
                "keys": list(self._cache.keys()),
            }


# 模块级单例
_cache = PromptCacheManager()


def cached_read(key: str, path: Path) -> str:
    """模块级便利函数：使用全局 _cache 单例读取。"""
    return _cache.get(key, path)


def invalidate_cache(key: str | None = None) -> None:
    """模块级便利函数：失效全局缓存。"""
    _cache.invalidate(key)


def cache_stats() -> dict:
    """模块级便利函数：返回缓存统计。"""
    return _cache.stats()

"""
引擎实例池 — 在 EngineManager 单例基础上扩展
解决高并发场景下的引擎复用问题
"""

from typing import Optional
from .. import EngineType, BaseBrowserEngine


class EnginePool:
    """
    引擎池 — 可选扩展，不属于原文核心逻辑
    仅在 EngineManager 单例实例数不足时启用
    """

    def __init__(self, pool_size: int = 2):
        self._pool: dict[EngineType, list[BaseBrowserEngine]] = {}
        self._pool_size = pool_size

    @property
    def pool_size(self) -> int:
        return self._pool_size

    def get_engines(self, engine_type: EngineType) -> list[BaseBrowserEngine]:
        """获取指定类型的引擎列表"""
        return self._pool.get(engine_type, [])

    async def release(self, engine: BaseBrowserEngine):
        """归还引擎到池中"""
        engine_type = engine.engine_type
        if engine_type not in self._pool:
            self._pool[engine_type] = []
        self._pool[engine_type].append(engine)

    async def warmup_all(self):
        """预热所有引擎 — 子类实现具体创建逻辑"""
        raise NotImplementedError("由子类实现具体预热逻辑")

    async def shutdown_all(self):
        """关闭所有池中引擎"""
        for engine_type, engines in self._pool.items():
            for engine in engines:
                try:
                    await engine.close()
                except Exception:
                    pass
        self._pool.clear()


__all__ = ["EnginePool"]

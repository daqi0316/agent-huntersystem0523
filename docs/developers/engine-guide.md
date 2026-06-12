# 浏览器引擎开发指南

> 适用于需要新增浏览器引擎类型的开发者。
> 读完本文，你会知道如何编写、注册、测试一个新的引擎实现。

---

## 架构概览

```
browser_engine/
├── __init__.py            ← EngineType / EngineStatus / BaseBrowserEngine 抽象
├── engine/
│   ├── http_engine.py     ← HTTP 直连（反爬等级 1）
│   ├── invisible_engine.py ← invisible_playwright（反爬等级 5，首选）
│   └── browser_use_engine.py ← browser-use（反爬等级 4，备用）
├── manager/
│   └── engine_manager.py  ← EngineManager 单例 + 降级链 + 平台映射
└── tests/
    └── test_engines.py    ← 接口契约测试
```

### 三层引擎关系

1. **首选引擎** — 对应平台反爬等级最高的引擎（如 BOSS 直聘 → invisible_playwright）
2. **备用引擎** — 首选失败时降级（如 browser-use）
3. **HTTP 直连** — 最终兜底，所有平台的最后手段

引擎选择在 `PLATFORM_ENGINE_MAP` 中声明，`fetch_with_fallback` 自动遍历降级链。

---

## 引擎抽象接口

每个引擎必须继承 `BaseBrowserEngine`（定义在 `__init__.py`），实现以下 5 个抽象方法：

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `engine_type` (property) | `EngineType` | 返回引擎类型枚举 |
| `capability` (property) | `EngineCapability` | 返回引擎能力描述 |
| `health_check()` | `EngineStatus` | 健康检查，返回 available / unavailable / degraded |
| `fetch_page(url, wait_for, timeout)` | `PageResult` | 获取页面内容的唯一入口 |
| `execute_script(script)` | `Any` | 执行 JavaScript（不支持则 raise NotImplementedError） |
| `close()` | `None` | 释放引擎资源 |

### 可选覆盖

- `warmup()` — 引擎预热，在 EngineLifecycleManager 启动时调用
- `reset()` — 重置引擎到初始状态
- `get_stats()` — 返回引擎运行时统计（自动继承基类实现）

---

## 核心数据结构

### EngineType（在 `__init__.py` 扩展）

```python
class EngineType(str, Enum):
    INVISIBLE_PLAYWRIGHT = "invisible_playwright"
    BROWSER_USE = "browser_use"
    HTTP = "http"
    # ── 预留 ──
    PLAYWRIGHT_DIRECT = "playwright_direct"
    SELENIUM = "selenium"
```

添加新引擎时，先在这里追加枚举值。

### EngineCapability

```python
@dataclass
class EngineCapability:
    engine_type: EngineType
    anti_crawl_level: int       # 1-5
    supports_javascript: bool
    supports_cdp: bool
    supports_stealth: bool
    recaptcha_score: float      # 0.0-1.0
    startup_time_ms: int        # 预热耗时
    memory_mb: int              # 内存占用评估
    max_concurrent_pages: int = 1
    supports_screenshot: bool = True
    version: str = "1.0.0"
```

- `anti_crawl_level` — 引擎能处理的最高反爬等级，用于 EngineManager 自动匹配
- `recaptcha_score` — reCAPTCHA v3 预期得分，`0.0` 表示无法绕过

### PageResult

```python
@dataclass
class PageResult:
    success: bool
    html: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    screenshot: Optional[bytes] = None
    error_message: Optional[str] = None
    engine_used: Optional[EngineType] = None
    retry_count: int = 0
    status_code: Optional[int] = None
    duration_ms: Optional[float] = None
    is_fallback: bool = False
```

**无论成功还是失败都必须返回 PageResult**（不要抛异常到上层）。失败时设 `success=False` + `error_message`。

---

## 分步指南：添加新引擎

### Step 1：注册引擎类型

在 `__init__.py` 的 `EngineType` 中添加：

```python
class EngineType(str, Enum):
    # ... 已有 ...
    CHROMIUM_CDP = "chromium_cdp"   # 新增
```

### Step 2：创建引擎文件

在 `engine/` 下创建 `chromium_cdp_engine.py`：

```python
"""
Chromium CDP 直连引擎 — 通过 Chrome DevTools Protocol 控制浏览器
"""

from .. import BaseBrowserEngine, EngineType, EngineStatus, EngineCapability, PageResult


class ChromiumCDPEngine(BaseBrowserEngine):
    """CDP 直连引擎，适用于需要 JS 渲染但不想用完整 invisible_playwright 的场景"""

    @property
    def engine_type(self) -> EngineType:
        return EngineType.CHROMIUM_CDP

    @property
    def capability(self) -> EngineCapability:
        return EngineCapability(
            engine_type=self.engine_type,
            anti_crawl_level=3,
            supports_javascript=True,
            supports_cdp=True,
            supports_stealth=False,
            recaptcha_score=0.3,
            startup_time_ms=2000,
            memory_mb=80,
        )

    async def health_check(self) -> EngineStatus:
        # 检查 Chrome 进程是否可达
        if await self._check_chrome_alive():
            return EngineStatus.AVAILABLE
        return EngineStatus.UNAVAILABLE

    async def fetch_page(self, url: str, wait_for: str | None = None, timeout: int = 30000) -> PageResult:
        try:
            # 通过 CDP 连接 Chrome 获取页面
            html = await self._cdp_fetch(url, timeout)
            return PageResult(success=True, html=html, engine_used=self.engine_type)
        except Exception as e:
            self.record_failure()
            return PageResult(success=False, error_message=str(e), engine_used=self.engine_type)

    async def execute_script(self, script: str) -> Any:
        return await self._cdp_evaluate(script)

    async def close(self):
        await self._cdp_disconnect()
```

### Step 3：注册到 EngineManager

两个位置需要修改：

**3a. 平台映射** — 在 `manager/engine_manager.py` 的 `PLATFORM_ENGINE_MAP` 中把平台映射到首选引擎类型：

```python
# engine_manager.py
PLATFORM_ENGINE_MAP: dict[str, EngineType] = {
    "boss_zhipin": EngineType.INVISIBLE_PLAYWRIGHT,

    # 新增
    "my_platform": EngineType.CHROMIUM_CDP,
}
```

**3b. 降级链** — 如果新引擎需要降级到其他引擎，在 `_DEFAULT_FALLBACK_CHAINS` 中注册：

```python
_DEFAULT_FALLBACK_CHAINS: dict[EngineType, EngineFallbackChain] = {
    EngineType.INVISIBLE_PLAYWRIGHT: EngineFallbackChain(
        primary=EngineType.INVISIBLE_PLAYWRIGHT,
        fallback=EngineType.BROWSER_USE,
        last_resort=EngineType.HTTP,
    ),

    # 新增引擎降级链
    EngineType.CHROMIUM_CDP: EngineFallbackChain(
        primary=EngineType.CHROMIUM_CDP,
        fallback=EngineType.BROWSER_USE,
        last_resort=EngineType.HTTP,
    ),
}
```

`fetch_with_fallback` 会按 primary → fallback → last_resort 顺序依次尝试。

### Step 4：编写测试

在 `tests/test_engines.py` 中追加：

```python
class TestChromiumCDPEngine:

    @pytest.mark.asyncio
    async def test_engine_type(self):
        engine = ChromiumCDPEngine({})
        assert engine.engine_type == EngineType.CHROMIUM_CDP

    @pytest.mark.asyncio
    async def test_capability(self):
        engine = ChromiumCDPEngine({})
        cap = engine.capability
        assert cap.anti_crawl_level == 3
        assert cap.supports_javascript is True

    @pytest.mark.asyncio
    async def test_health_check(self):
        engine = ChromiumCDPEngine({})
        status = await engine.health_check()
        assert status in (EngineStatus.AVAILABLE, EngineStatus.UNAVAILABLE)
```

然后在 `tests/test_manager.py` 中追加降级链测试：

```python
@pytest.mark.asyncio
async def test_my_platform_fallback_chain():
    manager = EngineManager()
    result = await manager.fetch_with_fallback(
        url="https://example.com",
        platform_name="my_platform",
    )
    assert result.success is True  # 验证降级链能正常走通
```

---

## 引擎注册到平台适配器

新建引擎后，平台适配器（如 `BossZhipinAdapterV3`）通过 EngineManager 间接使用引擎：

```python
class BossZhipinAdapterV3(PlatformAdapter):
    def __init__(self, config, proxy_pool=None):
        self._engine_manager = EngineManager(config.get("engine_manager", {}) if config else {})

    async def health_check(self) -> str:
        health = await self._engine_manager.health_check_all()
        if health.get(EngineType.INVISIBLE_PLAYWRIGHT) == EngineStatus.AVAILABLE:
            return "healthy"
        return "down"
```

平台适配器不需要知道引擎内部实现，只通过 `EngineType` 枚举健康状态。

---

## 最佳实践

### 1. 总是返回 PageResult，不抛异常
```python
# ✅ 正确
return PageResult(success=False, error_message=str(e), engine_used=self.engine_type)

# ❌ 错误
raise e
```

### 2. 连续失败自动标记不可用
基类 `record_failure()` 会在连续失败达到 `_failure_threshold`（默认 3）后自动标记引擎为 UNAVAILABLE。引擎实现只需在 `fetch_page` 的 except 块中调用 `self.record_failure()`。

### 3. 不要在 `__init__` 中创建重量级资源
引擎实例在 EngineManager 首次使用时才创建（`_get_or_create_engine`），但 `__init__` 中应只做轻量初始化。重量资源（浏览器进程、网络连接）放到 `fetch_page` 首次调用或 `warmup()` 中。

### 4. 引擎关闭要幂等
`close()` 应该能被多次调用而不会报错。如果资源已关闭，直接 pass。

### 5. 能力声明要诚实
`anti_crawl_level` 和 `recaptcha_score` 影响 EngineManager 的平台匹配决策。报高了会导致反爬失败，报低了会导致引擎被跳过。

---

## 测试清单

新引擎交付前确认：

- [ ] `engine_type` 返回正确的 `EngineType` 枚举
- [ ] `capability` 的能力等级与实现一致
- [ ] `health_check` 在有无资源时返回正确状态
- [ ] `fetch_page` 成功返回 `success=True` + `html`
- [ ] `fetch_page` 失败返回 `success=False` + `error_message`
- [ ] `execute_script` 支持/正确 raise NotImplementedError
- [ ] `close` 幂等可重复调用
- [ ] 已加入 `PLATFORM_ENGINE_MAP`（如果适用）
- [ ] 单元测试覆盖正常路径 + 错误路径
- [ ] 降级链集成测试通过

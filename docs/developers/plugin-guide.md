# 引擎插件开发指南

> 适用于需要扩展引擎行为的开发者——截图、录制、监控、自定义逻辑。
> 读完本文，你会知道如何编写、注册、测试一个新的引擎插件。

---

## 架构概览

```
browser_engine/plugins/
├── base.py         ← EnginePlugin 基类 + PluginRegistry 注册表
├── registry.py     ← register_default_plugins() 便捷入口
└── __init__.py
```

### 插件生命周期

插件通过三个 hook 方法介入引擎的工作流：

```
fetch_page(url)
    │
    ├── on_fetch_start(url, engine_type)    ← 返回额外配置 dict
    │
    ├── fetch 成功 → on_fetch_complete(url, result, engine_type)
    │
    └── fetch 失败 → on_error(url, exception, engine_type)
```

---

## 插件基类

```python
class EnginePlugin(ABC):
    name: str = ""          # 插件唯一标识
    version: str = "1.0.0"
    description: str = ""

    @abstractmethod
    async def on_fetch_start(self, url: str, engine_type: EngineType) -> dict | None:
        """fetch 开始时调用

        返回 dict 会合并到 fetch_page 的 kwargs 中（如 {"capture_screenshot": True}）。
        返回 None 则不传递额外参数。
        """

    @abstractmethod
    async def on_fetch_complete(self, url: str, result: PageResult, engine_type: EngineType):
        """fetch 成功完成时调用

        result 包含页面 HTML、截图、耗时等数据。
        此方法不应修改 result，只做消费（写文件、记录、发送）。
        """

    @abstractmethod
    async def on_error(self, url: str, error: Exception, engine_type: EngineType):
        """fetch 出错时调用

        error 为 fetch_page 内部捕获的原始异常。
        不要在此方法中重试，重试由中间件管道处理。
        """
```

---

## PluginRegistry API

插件注册表是一个全局 classmethod-only 注册表：

| 方法 | 说明 |
|------|------|
| `PluginRegistry.register(plugin)` | 注册一个插件实例。如果 name 已存在会覆盖并打警告 |
| `PluginRegistry.get(name)` | 按 name 获取插件，不存在返回 None |
| `PluginRegistry.list_plugins()` | 返回所有已注册插件的信息列表 |
| `PluginRegistry.unregister(name)` | 注销插件 |
| `PluginRegistry.clear()` | 清空所有插件 |

---

## 分步指南：编写一个插件

### Step 1：创建插件类

```python
# my_plugin.py
from app.tools.browser_engine.plugins.base import EnginePlugin, PluginRegistry
from app.tools.browser_engine import PageResult, EngineType


class AlertOnErrorPlugin(EnginePlugin):
    """错误告警插件 — 引擎 fetch 失败时发送通知"""

    name = "alert_on_error"
    version = "1.0.0"
    description = "引擎 fetch 失败时发送飞书/企业微信告警"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def on_fetch_start(self, url: str, engine_type: EngineType) -> dict | None:
        # 不需要修改 fetch 参数
        return None

    async def on_fetch_complete(self, url: str, result: PageResult, engine_type: EngineType):
        # 正常完成，无操作
        pass

    async def on_error(self, url: str, error: Exception, engine_type: EngineType):
        """引擎错误时发送告警"""
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json={
                "msgtype": "text",
                "text": {
                    "content": f"[引擎告警] {engine_type.value} 请求 {url} 失败: {error}",
                },
            })
```

### Step 2：注册插件

```python
# 在应用启动时注册
PluginRegistry.register(AlertOnErrorPlugin(webhook_url="https://hooks.example.com/alert"))
```

或通过 `register_default_plugins()` 扩展（编辑 `plugins/registry.py`）：

```python
def register_default_plugins():
    global _registered
    if _registered:
        return

    PluginRegistry.register(ScreenshotCapturePlugin())
    PluginRegistry.register(RequestRecorderPlugin())
    PluginRegistry.register(AlertOnErrorPlugin(webhook_url="..."))  # 新增
    _registered = True
```

### Step 3：验证注册状态

```python
>>> PluginRegistry.list_plugins()
[
    {"name": "screenshot_capture", "version": "1.0.0", "description": "采集页面时自动截取调试截图"},
    {"name": "request_recorder",   "version": "1.0.0", "description": "记录所有引擎请求的 URL、耗时、结果"},
    {"name": "alert_on_error",     "version": "1.0.0", "description": "引擎 fetch 失败时发送飞书/企业微信告警"},
]
```

---

## 内置插件参考

### ScreenshotCapturePlugin

- **name**: `screenshot_capture`
- **功能**: fetch 完成后将 `result.screenshot` 保存到磁盘
- **配置**: `output_dir`（默认 `/tmp/engine-screenshots`）
- **hook 用途**: `on_fetch_start` 返回 `{"capture_screenshot": True}` 告诉引擎需要截图；
  `on_fetch_complete` 把截图写入文件

### RequestRecorderPlugin

- **name**: `request_recorder`
- **功能**: 记录所有 fetch 请求的 URL、引擎、耗时、结果
- **数据**: 保存在 `records: list[dict]` 属性中，可导出查看
- **hook 用途**: `on_fetch_start` 记录开始时间戳；
  `on_fetch_complete` / `on_error` 记录完整请求记录

---

## 插件与中间件的区别

| 维度 | 插件 (Plugin) | 中间件 (Middleware) |
|------|-------------|-------------------|
| 作用域 | 引擎层 — 单个引擎实例的 fetch 生命周期 | 管道层 — 所有引擎的请求/响应管道 |
| Hook 时机 | on_fetch_start / on_complete / on_error | before_fetch / after_fetch（管道注册） |
| 典型用途 | 截图、录制、告警、统计 | 重试、超时、代理选择、指标采集 |
| 可修改请求 | 返回 dict 合并到 kwargs，不能拦截 | 可以拦截、修改、重试请求 |
| 性能开销 | 低（异步 hook，不阻塞链） | 较高（管道内串行） |

**选型建议**：
- 只需要消费事件（日志、截图、告警）→ 插件
- 需要干预请求（重试、换代理、降级）→ 中间件
- 两者可以共存，互不干扰

---

## 测试插件

### 单元测试

```python
import pytest
from app.tools.browser_engine import PageResult, EngineType
from app.tools.browser_engine.plugins.base import PluginRegistry, RequestRecorderPlugin


class TestRequestRecorderPlugin:

    @pytest.mark.asyncio
    async def test_on_fetch_start_returns_none(self):
        plugin = RequestRecorderPlugin()
        result = await plugin.on_fetch_start("https://example.com", EngineType.HTTP)
        assert result is None

    @pytest.mark.asyncio
    async def test_on_fetch_complete_records_success(self):
        plugin = RequestRecorderPlugin()
        result = PageResult(success=True, html="<html/>", engine_used=EngineType.HTTP)

        await plugin.on_fetch_complete("https://example.com", result, EngineType.HTTP)

        assert len(plugin.records) == 1
        assert plugin.records[0]["url"] == "https://example.com"
        assert plugin.records[0]["success"] is True

    @pytest.mark.asyncio
    async def test_on_error_records_failure(self):
        plugin = RequestRecorderPlugin()

        await plugin.on_error("https://example.com", ValueError("fail"), EngineType.HTTP)

        assert len(plugin.records) == 1
        assert plugin.records[0]["success"] is False
        assert "error" in plugin.records[0]
```

### 注册表测试

```python
class TestPluginRegistry:

    def test_register_and_get(self):
        plugin = RequestRecorderPlugin()
        PluginRegistry.register(plugin)
        assert PluginRegistry.get("request_recorder") is plugin

    def test_list_plugins(self):
        plugins = PluginRegistry.list_plugins()
        assert any(p["name"] == "request_recorder" for p in plugins)

    def test_unregister(self):
        PluginRegistry.register(RequestRecorderPlugin())
        PluginRegistry.unregister("request_recorder")
        assert PluginRegistry.get("request_recorder") is None

    def test_clear(self):
        PluginRegistry.clear()
        assert len(PluginRegistry.list_plugins()) == 0
```

---

## 最佳实践

### 1. 插件要轻量
插件 hook 在每次 `fetch_page` 调用中同步执行。不要在 hook 中做重量操作（如调用外部 API 同步等待）。如果需要，启用自己的后台任务。

### 2. on_fetch_complete 不要修改 result
`PageResult` 传入的是引用，但修改它会影向上游。插件应该只消费，不篡改。

### 3. 插件没有执行顺序保证
当前 `PluginRegistry` 不保证插件执行顺序。如果插件之间有依赖，应该合并到一个插件中。

### 4. on_fetch_start 返回 dict 的约定
返回的 dict 会解包到 `fetch_page` 的 kwargs 中。引擎实现需要支持这些参数才有效。标准参数：
- `capture_screenshot: bool` — 是否返回截图
- `wait_for_selector: str` — 等待特定元素出现

### 5. 插件实例可以持有状态
与中间件不同，每个 `PluginRegistry.register()` 保存的是插件**实例**。你可以在插件内维护状态（如 `RequestRecorderPlugin.records`），但要注意多线程/协程安全。

---

## 测试清单

插件交付前确认：

- [ ] `name` 是唯一的且语义明确
- [ ] 三个 hook 方法都实现了（`on_fetch_start`, `on_fetch_complete`, `on_error`）
- [ ] `on_fetch_start` 返回 `None` 或合法的 dict
- [ ] `on_fetch_complete` 不修改 `result`
- [ ] 单元测试覆盖成功路径和错误路径
- [ ] 注册表测试覆盖 register / get / unregister / clear
- [ ] 没有阻塞操作（如果不可避免，使用 `asyncio.create_task` 剥离）

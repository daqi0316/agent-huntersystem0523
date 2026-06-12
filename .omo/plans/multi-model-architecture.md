# 多模型接入架构规划（修正版 v2）

> 状态：规划稿 v2 — 经 Momus 审核后修正
> 目标：使用者选模型、填 Key、就能用。工程化、深度化、长远化、模块化、可扩展设计。

---

## 一、设计原则

1. **使用者视角 = 简单的**：选一个主模型、填 Key、保存。再选一个备用的。仅此而已。
2. **代码视角 = 工程化的**：类型安全、连接池、缓存、错误分类、加密、测试覆盖。
3. **长远视角 = 可扩展的**：现在不需要的字段（capabilities）先留好，将来加功能不改表。

---

## 二、数据模型

```sql
CREATE TYPE llm_provider_type AS ENUM (
    'openai_compat',   -- OpenAI / DeepSeek / Qwen / OMLX / vLLM / 任何兼容 API
    'anthropic'        -- Claude 系列
    -- 扩展：新增类型只加一个 enum value + 一个 Provider 类
);

CREATE TABLE llm_providers (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name              VARCHAR(100) NOT NULL,         -- 展示名 "DeepSeek V3"
    provider_type     llm_provider_type NOT NULL,     -- 枚举约束，杜绝脏数据

    -- 连接配置
    base_url          VARCHAR(1024) NOT NULL,          -- 长路径自定义地址能存下
    model_name        VARCHAR(200) NOT NULL,           -- API 用的 model 名
    api_key_enc       TEXT,                            -- AES-256-GCM 加密，NULL = 本地模型
    key_salt          VARCHAR(64),                     -- 密钥派生盐，支持密钥轮换
    key_updated_at    TIMESTAMPTZ,                     -- 上次换 Key 时间

    -- 运行时参数（可调）
    timeout_seconds   INT DEFAULT 30,                  -- 单次请求超时
    max_retries       INT DEFAULT 2,                   -- 失败重试次数（401 不重试）

    -- 能力声明（JSONB — 未来路由的基础，现在先存着）
    capabilities      JSONB NOT NULL DEFAULT '{
        "chat": true,
        "function_calling": true,
        "streaming": false,
        "embedding": false,
        "vision": false,
        "max_context_window": 128000,
        "max_output_tokens": 4096
    }',

    -- 主备标记（应用层保证：全表最多一个 is_primary=true，最多一个 is_fallback=true）
    is_primary        BOOLEAN NOT NULL DEFAULT FALSE,
    is_fallback       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,   -- 系统禁用（如健康检查连续失败）

    -- 排序 + 元数据
    sort_order        INT DEFAULT 100,                 -- 列表展示顺序
    notes             TEXT,                            -- 使用者备注

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT unique_primary CHECK (
        NOT (is_primary AND is_fallback)              -- 不能同时是主和备
    )
);

-- 部分唯一索引：确保主/备各只有一个
CREATE UNIQUE INDEX idx_llm_providers_single_primary
    ON llm_providers (is_primary) WHERE is_primary = TRUE;
CREATE UNIQUE INDEX idx_llm_providers_single_fallback
    ON llm_providers (is_fallback) WHERE is_fallback = TRUE;

-- 索引
CREATE INDEX idx_llm_providers_active ON llm_providers (is_active) WHERE is_active = TRUE;
```

### 字段设计理由

| 字段 | 为什么要有？ |
|------|------------|
| `key_salt` | 将来换加密密钥时，通过 salt 判断是老版本加密，触发重新加密 |
| `key_updated_at` | 管理页面展示"Key 上次更新于 3 个月前"，提醒轮换 |
| `capabilities` | 现在不路由，但数据先存好。将来加路由不用 migration |
| `timeout_seconds` | 本地 OMLX（3s）和远程 GPT-4o（30s）延迟差异大，不合理共用 |
| `max_retries` | 同上。429 限流可重试，401 禁止重试（由 Provider 层判断） |
| `sort_order` | 管理列表可以手动排序，常用模型排前面 |
| `notes` | 使用者记录"这个 Key 是公司的，那个是我私人的" |

---

## 三、Provider 层设计

### 3.1 接口

```python
class ChatResult(TypedDict):
    content: str
    model: str              # 实际使用的 model
    usage: dict | None      # {"prompt_tokens": N, "completion_tokens": N}
    provider: str           # provider_type


class ProviderError(Exception):
    category: ErrorCategory  # AUTH / RATE_LIMIT / TIMEOUT / SERVER_ERROR / UNKNOWN

    def should_retry(self) -> bool: ...     # 401 → False, 429 → True
    def should_fallback(self) -> bool: ...   # 401 → False, 500 → True


class BaseProvider(ABC):
    provider_type: str

    @abstractmethod
    async def chat(
        self, model: str, messages: list[dict], **kwargs
    ) -> ChatResult: ...

    @abstractmethod
    async def chat_stream(
        self, model: str, messages: list[dict], **kwargs
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def embed(
        self, model: str, texts: list[str]
    ) -> list[list[float]]:
        """不支持时抛 NotImplementedError，由 Router 处理降级"""
        ...

    @abstractmethod
    async def check_connection(self) -> ConnectionResult:
        """发一条"Hi"看回复，验证 Key + 模型都可用"""
        ...
```

### 3.2 OpenAICompatProvider

```python
class OpenAICompatProvider(BaseProvider):
    """统一所有 OpenAI-compatible API。
    
    覆盖：OpenAI / DeepSeek / Qwen / Zhipu / OMLX / vLLM / Ollama / 任何兼容 API
    
    核心逻辑：
    - 复用 httpx.AsyncClient 连接池（按 base_url 分组）
    - 错误分类：解析 HTTP status code + error body
      - 401 → ProviderError(category=AUTH, should_retry=False)
      - 429 → ProviderError(category=RATE_LIMIT, should_retry=True)
      - 500+ → ProviderError(category=SERVER_ERROR, should_retry=True)
      - timeout → ProviderError(category=TIMEOUT, should_retry=True)
    """
    _client_pool: dict[str, AsyncOpenAI]  # base_url → client（连接复用）

    async def chat(self, model, messages, **kwargs) -> ChatResult:
        client = self._get_client(base_url)
        try:
            resp = await client.chat.completions.create(
                model=model, messages=messages, **kwargs
            )
            return ChatResult(
                content=resp.choices[0].message.content or "",
                model=resp.model,
                usage=resp.usage.model_dump() if resp.usage else None,
                provider="openai_compat",
            )
        except APIConnectionError as e:
            raise ProviderError(category=TIMEOUT, ...)
        except AuthenticationError as e:
            raise ProviderError(category=AUTH, should_retry=False, ...)
        except RateLimitError as e:
            raise ProviderError(category=RATE_LIMIT, should_retry=True, ...)
        except APIStatusError as e:
            if e.status_code >= 500:
                raise ProviderError(category=SERVER_ERROR, ...)
            raise ProviderError(category=UNKNOWN, ...)
```

**连接池策略**：按 `base_url` 分组缓存 `AsyncOpenAI` 实例，Provider 配置变更时清空对应缓存。

```python
class ProviderPool:
    """Provider 连接池，管理所有 provider 的长连接。"""
    
    _clients: dict[str, AsyncOpenAI]    # base_url → client
    _providers: dict[str, BaseProvider] # provider_type → provider 实例
    
    async def get_provider(self, provider_type: str) -> BaseProvider: ...
    async def execute_chat(self, provider_cfg: ProviderConfig, ...) -> ChatResult: ...
    def invalidate(self, base_url: str): ...  # 配置变更时清对应连接
```

### 3.3 AnthropicProvider

```python
class AnthropicProvider(BaseProvider):
    """Claude 系列专用。
    
    和 OpenAI 的关键差异（实现时必须处理）：
    
    消息格式：
        OpenAI:  [{role: "user", content: "hello"}]
        Claude:  [{role: "user", content: [{type: "text", text: "hello"}]}]
    
    工具调用：
        OpenAI:  tools=[{"type": "function", "function": {...}}]
        Claude:  tools=[{"name": "...", "input_schema": {...}}]
    
    Stream 格式：
        OpenAI:  data: {"choices":[{"delta":{"content":"..."}}]}
        Claude:  event: content_block_delta / content_block_stop
    
    实现路径：
    - 用 anthropic SDK（pip install anthropic）
    - 消息格式转换（维护一个 OpenAI→Claude 适配函数）
    - 工具调用格式转换
    """
    
    async def chat(self, model, messages, **kwargs) -> ChatResult:
        # 转换消息格式
        claude_messages = self._convert_messages(messages)
        # 转换 tools 格式
        claude_tools = self._convert_tools(kwargs.pop("tools", []))
        # 调用 Claude API
        resp = await self._client.messages.create(
            model=model,
            messages=claude_messages,
            tools=claude_tools or NOT_GIVEN,
            **kwargs,
        )
        # 转回 OpenAI 兼容的 response 格式
        return ChatResult(
            content=resp.content[0].text,
            model=resp.model,
            usage={"prompt_tokens": resp.usage.input_tokens, ...},
            provider="anthropic",
        )
```

> AnthropicProvider 不能走 OpenAI-compat 路线，因为 Claude 的消息格式、工具格式、Stream 格式都不兼容。必须单独实现。但接口返回统一，上层无感知。

---

## 四、Router 层设计（轻量版）

```python
class ModelRouter:
    """模型路由：查主模型 → 调 API → 失败降级 → 返回。
    
    不做过往规划里的复杂路由。只做：
    1. 查 is_primary → 调 → 成功？返回
    2. 失败 → 查 is_fallback → 调 → 成功？返回
    3. 全失败 → 报错
    """

    # Provider 缓存（按 provider_type）
    _providers: dict[str, BaseProvider] = {}
    
    # 主备缓存（30s TTL，减少 DB 查询）
    _cached_primary: ProviderConfig | None = None
    _cached_fallback: ProviderConfig | None = None
    _cache_updated_at: float = 0
    CACHE_TTL: float = 30.0

    async def _load_configs(self) -> tuple[ProviderConfig | None, ProviderConfig | None]:
        """从缓存 or DB 读主备配置。30s 刷新一次。"""
        now = time.monotonic()
        if now - self._cache_updated_at < self.CACHE_TTL:
            return self._cached_primary, self._cached_fallback
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(LlmProvider).where(
                    or_(LlmProvider.is_primary == True, LlmProvider.is_fallback == True)
                )
            )
            providers = result.scalars().all()
            # ... 映射到 ProviderConfig
            self._cached_primary = primary_config
            self._cached_fallback = fallback_config
            self._cache_updated_at = now
            return primary_config, fallback_config

    async def chat(self, messages, **kwargs) -> ChatResult:
        primary, fallback = await self._load_configs()
        errors = []

        # 尝试主模型
        if primary:
            try:
                provider = self._get_provider(primary.provider_type)
                return await provider.chat(primary.model_name, messages, **kwargs)
            except ProviderError as e:
                errors.append(("primary", e))
                if not e.should_fallback():
                    raise  # 401 不降级，直接抛

        # 降级到备用
        if fallback:
            try:
                provider = self._get_provider(fallback.provider_type)
                return await provider.chat(fallback.model_name, messages, **kwargs)
            except ProviderError as e:
                errors.append(("fallback", e))

        raise AllProvidersFailed(errors)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        primary, fallback = await self._load_configs()
        
        # 优先主模型
        if primary:
            try:
                provider = self._get_provider(primary.provider_type)
                return await provider.embed(primary.model_name, texts)
            except NotImplementedError:
                pass  # 主模型不支持，fallback
        
        # 兜底：用 LLM_EMBED_MODEL 环境变量或找一个支持 embed 的
        embed_cfg = await self._find_embed_model()
        if embed_cfg:
            provider = self._get_provider(embed_cfg.provider_type)
            return await provider.embed(embed_cfg.model_name, texts)
        
        raise EmbeddingNotAvailable()

    def _get_provider(self, provider_type: str) -> BaseProvider:
        """Provider 实例懒加载 + 缓存。"""
        if provider_type not in self._providers:
            if provider_type == "openai_compat":
                self._providers[provider_type] = OpenAICompatProvider()
            elif provider_type == "anthropic":
                self._providers[provider_type] = AnthropicProvider()
            else:
                raise ValueError(f"Unknown provider type: {provider_type}")
        return self._providers[provider_type]
```

---

## 五、错误分类与处理策略

```python
@dataclass
class ProviderError(Exception):
    category: ErrorCategory
    message: str
    status_code: int | None = None
    provider: str | None = None

class ErrorCategory(Enum):
    AUTH          = "auth"           # API Key 错误 / 无权访问 → 不重试、不降级
    RATE_LIMIT    = "rate_limit"     # 限流 → 退避重试、不降级
    TIMEOUT       = "timeout"        # 超时 → 重试、可降级
    SERVER_ERROR  = "server_error"   # 5xx → 重试、可降级
    INVALID_MODEL = "invalid_model"  # model 不存在 → 不重试
    CONTEXT_TOO_LONG = "context_too_long"
    UNKNOWN       = "unknown"        # 兜底

# 处理策略矩阵
STRATEGY: dict[ErrorCategory, Strategy] = {
    AUTH:          Strategy(retryable=False, fallback=False,  alert=True),
    RATE_LIMIT:    Strategy(retryable=True,  fallback=False,  alert=False),
    TIMEOUT:       Strategy(retryable=True,  fallback=True,   alert=False),
    SERVER_ERROR:  Strategy(retryable=True,  fallback=True,   alert=True),
    INVALID_MODEL: Strategy(retryable=False, fallback=False,  alert=True),
    UNKNOWN:       Strategy(retryable=False, fallback=True,   alert=True),
}
```

---

## 六、管理 API

```python
# ── 模型配置 ──
GET    /api/v1/admin/llm/providers              # 列表（含预设）
POST   /api/v1/admin/llm/providers              # 新增
PUT    /api/v1/admin/llm/providers/:id          # 编辑
DELETE /api/v1/admin/llm/providers/:id          # 删除

# ── 主备切换（带约束检查） ──
POST   /api/v1/admin/llm/providers/:id/primary  # 设为主模型（自动取消旧 primary）
POST   /api/v1/admin/llm/providers/:id/fallback # 设为备用（自动取消旧 fallback）
POST   /api/v1/admin/llm/providers/:id/unset    # 取消主/备标记

# ── 测试+健康 ──
POST   /api/v1/admin/llm/providers/:id/test     # 发一条 "Hi" 验证连通性 + Key 有效
GET    /api/v1/admin/llm/health                 # 所有 active 模型的健康状态

# ── 可用预设列表 ──
GET    /api/v1/admin/llm/presets                # 返回可选的预设模板列表
```

### API 安全

- Key 写入时加密，读出时 mask（`sk-****abcd`），不允许前端回显全文
- 所有管理 API 需管理员权限（`is_admin=True`）

---

## 七、向后兼容策略

```
┌─ 启动时 ─────────────────────────────┐
│                                      │
│  llm_providers 表有 primary 记录？     │
│    ├── YES → 用 DB 配置，忽略环境变量   │
│    │                                      │
│    └── NO → 检查 LLM_PROVIDER 环境变量？  │
│         ├── YES → 用 env 构造临时 config  │
│         │        行为与现在完全一致        │
│         │                                │
│         └── NO → 系统提示"请配置模型"      │
│                  ├── 已有 LLM 调用会报错   │
│                  └── 管理页面可配置         │
└────────────────────────────────────────┘
```

**旧文件废弃路径**：

| 旧文件 | 废弃策略 |
|--------|---------|
| `app/llm/omlx_client.py` | 加 `@deprecated("Use OpenAICompatProvider")` 注释，保留 1 个版本 |
| `app/llm/vllm_client.py` | 同上 |
| `app/llm/cn_providers.py` | 同上 |
| `app/llm/base.py` | `LLMClient` 保留，新 `BaseProvider` 走独立继承链。两个接口共存过渡 |

---

## 八、缓存策略

```python
class ProviderConfigCache:
    """主备配置缓存，减少 DB 查询压力。
    
    缓存键: "llm:router:providers"
    过期策略: TTL 30s（管理页面改配置后最多 30s 生效）
    失效策略: 管理 API 写操作后主动 invalidate
    """
    TTL = 30  # 秒

    async def get(self) -> tuple[ProviderConfig | None, ProviderConfig | None]:
        # 1. 查 Redis（快路径）
        # 2. 没有 → 查 DB（慢路径）
        # 3. 写入 Redis
        # 4. 返回

    async def invalidate(self):
        # 管理 API 写操作后调用
        # 删除 Redis key
```

没 Redis 时退化为进程内 dict 缓存。

---

## 九、预设种子

### 种子数据（在 migration 中管理）

```python
"""versions/xxxx_add_llm_providers.py"""

PRESETS = [
    {
        "name": "本地 OMLX",
        "provider_type": "openai_compat",
        "base_url": "http://localhost:8000/v1",
        "model_name": "Qwen3.6-35B-A3B-4bit",
        "api_key_enc": None,           # 本地模型不需要 Key
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": True, "vision": False,
                         "max_context_window": 128000, "max_output_tokens": 4096},
        "is_primary": True,
        "is_fallback": False,
        "timeout_seconds": 30,
        "max_retries": 2,
        "sort_order": 10,
    },
    {
        "name": "DeepSeek V3",
        "provider_type": "openai_compat",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
        "api_key_enc": None,           # 用户自己填
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": False,  # DeepSeek 不支持 embed
                         "vision": False,
                         "max_context_window": 128000, "max_output_tokens": 8192},
        "is_primary": False,
        "is_fallback": True,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 20,
    },
    {
        "name": "GPT-4o",
        "provider_type": "openai_compat",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "api_key_enc": None,
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": True, "vision": True,
                         "max_context_window": 128000, "max_output_tokens": 16384},
        "is_primary": False,
        "is_fallback": False,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 30,
    },
    {
        "name": "Claude Sonnet",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model_name": "claude-sonnet-4-20250514",
        "api_key_enc": None,
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": False, "vision": True,
                         "max_context_window": 200000, "max_output_tokens": 8192},
        "is_primary": False,
        "is_fallback": False,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 40,
    },
    {
        "name": "通义千问 Max",
        "provider_type": "openai_compat",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-max",
        "api_key_enc": None,
        "capabilities": {"chat": True, "function_calling": True, "streaming": True,
                         "embedding": True, "vision": True,
                         "max_context_window": 128000, "max_output_tokens": 8192},
        "is_primary": False,
        "is_fallback": False,
        "timeout_seconds": 60,
        "max_retries": 3,
        "sort_order": 50,
    },
]
```

种子数据的升级策略：后续如 base_url 或预设模型变更，通过新的 migration 做 `UPDATE`，不硬编码在业务代码中。

---

## 十、实施计划 — TODO

### Step 1：数据层（4 todos）

- [ ] **P1 1.1** `app/llm/models/llm_provider.py`: 创建 `LlmProvider` SQLAlchemy 模型
  - 字段：id(UUID) / name / provider_type(Enum) / base_url / model_name
  - 字段：api_key_enc(Text) / key_salt / key_updated_at
  - 字段：timeout_seconds(Int,default=30) / max_retries(Int,default=2)
  - 字段：capabilities(JSONB) / is_primary(Bool) / is_fallback(Bool) / is_active(Bool)
  - 字段：sort_order(Int) / notes(Text) / created_at / updated_at
  - 约束：`__table_args__` 唯一索引（is_primary WHERE true + is_fallback WHERE true）
  - 引用 `app.core.database.Base`

- [ ] **P1 1.2** Alembic migration: 建 `llm_provider_type` enum + `llm_providers` 表
  - `sa.Enum('openai_compat', 'anthropic', name='llm_provider_type')`
  - 所有字段 + UNIQUE 部分索引 + `server_default=func.now()`
  - 自动生成 migration 后用 `sa_op.create_type` + `sa_op.create_table` 手动调整

- [ ] **P1 1.3** Alembic migration: 插入 5 条种子预设数据（本地 OMLX / DeepSeek / GPT-4o / Claude / 通义千问）
  - `op.execute(insert(llm_providers_table).values(PRESETS))`
  - 本地 OMLX 设为 `is_primary=True`，DeepSeek 设为 `is_fallback=True`

- [ ] **P2 1.4** `tests/test_llm_models.py`: 测试 LlmProvider 模型
  - 测试：创建实例 + 默认值 + capabilities JSONB 读写
  - 测试：唯一索引约束（两个 primary 应该报错）
  - 测试：CHECK 约束（is_primary + is_fallback 不能同时 true）

### Step 2：Provider 层（5 todos）

- [ ] **P1 2.1** `app/llm/provider/base.py`: 实现 `BaseProvider` ABC
  - `ChatResult` TypedDict(content / model / usage / provider)
  - `ErrorCategory` Enum(AUTH / RATE_LIMIT / TIMEOUT / SERVER_ERROR / INVALID_MODEL / CONTEXT_TOO_LONG / UNKNOWN)
  - `ProviderError(Exception)` → category + message + status_code + should_retry() + should_fallback()
  - `STRATEGY` dict: 每种 ErrorCategory 的处理策略
  - `BaseProvider` ABC: `chat()` / `chat_stream()` / `embed()` / `check_connection()`

- [ ] **P1 2.2** `app/llm/provider/openai_compat.py`: 实现 `OpenAICompatProvider`
  - 继承 `BaseProvider`，provider_type=`"openai_compat"`
  - `_client: AsyncOpenAI` 连接池管理（按 base_url 缓存）
  - `chat()`: 调 OpenAI-compatible API，捕获异常并分类
  - `chat_stream()`: SSE 流式响应（AsyncIterator[str]）
  - `embed()`: 调 embeddings API
  - `check_connection()`: 发 "Hi" 验证 Key + 模型有效
  - 错误分类：APIConnectionError→TIMEOUT, AuthenticationError→AUTH, RateLimitError→RATE_LIMIT, APIStatusError(5xx)→SERVER_ERROR

- [ ] **P1 2.3** `app/llm/provider/anthropic.py`: 实现 `AnthropicProvider`
  - 继承 `BaseProvider`，provider_type=`"anthropic"`
  - 使用 `anthropic.AsyncAnthropic` SDK
  - `_convert_messages()`: OpenAI 消息格式 → Claude 消息格式（ContentBlock）
  - `_convert_tools()`: OpenAI tools 格式 → Claude tools 格式
  - `chat()`: 调 Claude Messages API，转回统一 ChatResult
  - `check_connection()`: 发 "Hi" 验证 Key 有效
  - embed() → raise NotImplementedError（Claude 不支持）

- [ ] **P2 2.4** `app/llm/provider/pool.py`: 实现 `ProviderPool`
  - `get_provider(provider_type: str) -> BaseProvider`：懒加载 + 缓存实例
  - `invalidate(provider_type: str)`：配置变更时清连接
  - 线程安全（asyncio.Lock）

- [ ] **P2 2.5** `tests/test_llm_providers.py`
  - 测试 OpenAICompatProvider：mock HTTP 响应，验证错误分类
  - 测试 AnthropicProvider：mock SDK，验证消息格式转换
  - 测试 ProviderError：should_retry / should_fallback 策略矩阵
  - 测试 ProviderPool：缓存 + invalidate

### Step 3：Router 层（3 todos）

- [ ] **P1 3.1** `app/llm/router/cache.py`: 实现 `ProviderConfigCache`
  - `get() -> tuple[ProviderConfig | None, ProviderConfig | None]`：读 Redis 或 DB
  - `invalidate()`：管理 API 写操作后调用
  - 30s TTL，无 Redis 时退化为进程内 dict
  - `ProviderConfig` dataclass：所有连接所需字段

- [ ] **P1 3.2** `app/llm/router/router.py`: 实现 `ModelRouter`
  - `chat(messages, **kwargs) -> ChatResult`：查主→调→失败→降级→报错
  - `embed(texts) -> list[list[float]]`：主模型→不支持→找 embed 模型→报错
  - `_get_provider(provider_type) -> BaseProvider`：从 ProviderPool 获取
  - `_find_embed_model()`：查 DB 找支持 embedding 的 active 模型
  - 401 错误不降级直接抛

- [ ] **P2 3.3** `tests/test_llm_router.py`
  - 测试：主模型成功→返回
  - 测试：主模型失败→降级到备用
  - 测试：主模型 401 不降级
  - 测试：embed 降级到备用模型
  - 测试：所有模型失败→AllProvidersFailed
  - 测试：缓存生效（30s 内不查 DB）

### Step 4：管理 API（6 todos）

- [ ] **P1 4.1** `app/llm/admin/api.py`: FastAPI router + Pydantic schemas
  - `ProviderCreate` / `ProviderUpdate` / `ProviderResponse` schema
  - `ProviderResponse.api_key` 永远 mask（`sk-****abcd`）
  - `GET /admin/llm/providers` — 列表（含预设 + 当前主备标记）
  - `POST /admin/llm/providers` — 新增（Key 加密存入）
  - `PUT /admin/llm/providers/{id}` — 编辑
  - `DELETE /admin/llm/providers/{id}` — 删除
  - `GET /admin/llm/presets` — 预设模板列表

- [ ] **P1 4.2** `app/llm/admin/api.py`: 主备切换端点
  - `POST /admin/llm/providers/{id}/primary` → 设为主模型，原 primary 自动取消
  - `POST /admin/llm/providers/{id}/fallback` → 设为备用，原 fallback 自动取消
  - `POST /admin/llm/providers/{id}/unset` → 取消主/备标记
  - 事务内完成 + 缓存 invalidate

- [ ] **P1 4.3** `app/llm/admin/api.py`: 测试 + 健康端点
  - `POST /admin/llm/providers/{id}/test` → 调 Provider.check_connection()
  - `GET /admin/llm/health` → 遍历所有 active 模型调 health，返回状态列表

- [ ] **P1 4.4** API Key 加密工具函数（放在 `app/llm/admin/crypto.py` 或复用 `account_manager.py`）
  - `encrypt_api_key(plain: str) -> str`：AES-256-GCM（Fernet）+ 生成 key_salt
  - `decrypt_api_key(enc: str) -> str`：解密
  - `mask_api_key(key: str) -> str`：`sk-****abcd` 格式

- [ ] **P2 4.5** 注册 admin API router 到 FastAPI
  - `app/main.py` 或 `app/api/admin.py`：`app.include_router(admin_llm_router, prefix="/api/v1")`
  - 添加管理员权限依赖（`get_current_admin_user`）

- [ ] **P2 4.6** `tests/test_llm_admin_api.py`
  - 测试 CRUD：创/读/改/删 provider
  - 测试：Key 存储加密，读出 mask
  - 测试：设为主 → 原主自动取消
  - 测试：设为备用 → 原备用自动取消
  - 测试：test 端点 mock 成功/失败
  - 测试：health 端点

### Step 5：集成（5 todos）

- [ ] **P1 5.1** `app/llm/__init__.py`: 修改 `get_llm_client()`
  - 查 DB 是否有 `is_primary=True` 的 provider
  - 有 → 用 Router 构造 client
  - 没有 → 用环境变量构造临时 client（向后兼容）
  - 导出 `get_model_router()` 新接口

- [ ] **P2 5.2** 旧 client 文件标记 `@deprecated`
  - `omlx_client.py`: 文件头加 `# @deprecated Use provider/openai_compat.py`
  - `vllm_client.py`: 同上
  - `cn_providers.py`: 同上
  - 不删代码，确保向后兼容

- [ ] **P2 5.3** 健康检查后台任务
  - `app/llm/admin/health_task.py`: `asyncio.create_task` 后台循环
  - 每 60s 遍历所有 `is_active=True` 的 provider
  - 调 `check_connection()`，连续失败 3 次→`is_active=False`，触发告警日志
  - 在 FastAPI lifespan 中启动

- [ ] **P2 5.4** `app/llm/__init__.py`: 注册管理员依赖 + 启动健康检查
  - `get_current_admin_user` 依赖（验证当前用户角色）
  - lifespan 事件中启动健康检查协程
  - 更新 `app/main.py` 引入 admin router

- [ ] **P2 5.5** `tests/test_llm_integration.py`
  - 全链路集成测试：创建 provider → 设为主 → get_llm_client() 返回 Router → chat() mock
  - 向后兼容测试：无 DB 记录时用 env 变量
  - 降级测试：主模型抛错 → 自动切备用

### Step 6：前端页面（独立 PR，4 todos，visual-engineering 分组）

- [ ] **P3 6.1** 前端路由 + 页面骨架
  - 页面路由: `/admin/settings/llm`
  - API 层调用封装（`adminApi.llm.*`）

- [ ] **P3 6.2** 模型列表组件
  - 表格展示所有 provider：名称/类型/模型名/状态(主/备/active)/Key 状态(已配置/未配置)
  - 行操作：编辑/删除/设为主/设为备用/测试连接

- [ ] **P3 6.3** 新增/编辑表单
  - 预设模板快速选择 → 自动填充 base_url + model_name
  - Key 输入（password 类型 mask）
  - 自定义字段: name / provider_type / base_url / model_name / key / timeout / max_retries

- [ ] **P3 6.4** 交互功能
  - 测试连接按钮（loading → 成功/失败提示）
  - 主/备切换确认弹窗
  - 删除确认弹窗
    
---

### 优先级说明

| 标记 | 含义 |
|------|------|
| P1 | 必须做，核心链路 |
| P2 | 要做，但可以排在 P1 之后 |
| P3 | 锦上添花，可延后 |

---

## 十一、文件最终结构

```
app/llm/
├── __init__.py                    # get_llm_client() 向后兼容 + get_model_router()
├── base.py                        # LLMClient（旧，保留不动）
├── retry.py                       # 不动
├── omlx_client.py                 # @deprecated 保留
├── vllm_client.py                 # @deprecated 保留
├── cn_providers.py                # @deprecated 保留
│
├── models/
│   └── llm_provider.py            # LlmProvider SQLAlchemy model
│
├── provider/
│   ├── __init__.py
│   ├── base.py                    # BaseProvider ABC + ChatResult + ProviderError
│   ├── openai_compat.py           # OpenAICompatProvider（连接池复用）
│   ├── anthropic.py               # AnthropicProvider（消息格式转换）
│   └── pool.py                    # ProviderPool（连接池管理）
│
├── router/
│   ├── __init__.py
│   ├── router.py                  # ModelRouter（主→备→报错）
│   └── cache.py                   # ProviderConfigCache（30s TTL）
│
└── admin/
    └── api.py                     # FastAPI router（管理端点）

tests/
├── test_llm_models.py             # 数据模型
├── test_llm_providers.py          # Provider 实现
├── test_llm_router.py             # 路由+降级
├── test_llm_admin_api.py          # 管理 API
└── test_llm_integration.py        # 全链路集成
```

---

## 十二、Momus 审核对照表

| # | Momus 问题 | v2 处理 |
|---|-----------|---------|
| 1 | `api_key_enc` 缺少密钥元数据 | ✅ 加了 `key_salt` + `key_updated_at` |
| 2 | `provider_type` 无约束 | ✅ 用 PostgreSQL ENUM |
| 3 | 主备一致性 | ✅ `UNIQUE` 部分索引 + 应用层事务 |
| 4 | 缺少 `capabilities` | ✅ JSONB 字段，预设值完整 |
| 5 | 无连接池 | ✅ `ProviderPool` 按 base_url 复用 |
| 6 | 错误不分类 | ✅ `ErrorCategory` + `STRATEGY` 矩阵 |
| 7 | Anthropic 没设计 | ✅ 详细实现路径 + 格式转换说明 |
| 8 | streaming 缺失 | ✅ 接口预置 `chat_stream()` + capabilities |
| 9 | embed 无降级 | ✅ `ModelRouter.embed()` 自动找能 embed 的模型 |
| 10 | test 无标准 | ✅ 发"Hi"验证 + 检查回复 |
| 11 | 每次查 DB | ✅ 30s TTL 缓存 |
| 12 | 无健康检查 | ✅ 后台任务 + `/admin/llm/health` |
| 13 | base_url 长度 | ✅ 1024 |
| 14 | 种子数据硬编码 | ✅ migration 管理 + 升级策略 |
| 15 | timeout/retries 不可配 | ✅ 每模型独立字段 |
| 16 | 旧文件处理 | ✅ `@deprecated` 过渡 |
| 17 | Key 前端安全 | ✅ mask + 不回显 |
| 18 | 缺少测试 | ✅ 每个 Step 有对应测试文件列表 |

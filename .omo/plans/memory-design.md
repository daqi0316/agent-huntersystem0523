# 跨会话记忆系统设计文档

> 对应 v4 Plan Phase 2a
> 作者：Sisyphus
> 状态：Momus 审查通过 (v2 修正: F1/F2/F3/M1/M2/M3/M4/V1/V2/V3)

---

## 1. 设计目标

让 AI 招聘助手在**跨会话**维度记住用户偏好、常用筛选条件、历史决策模式，并在新会话中主动注入相关记忆，减少重复输入，提升效率。

### 非目标（不做什么）

- 不存储原始对话全文（仅存 LLM 摘要）
- 不做用户行为画像建模
- 不改已有 Agent 接口签名
- 不做实时同步（摘要生成是异步的，不阻塞主流程）
- 不做文件系统 FTS5

---

## 2. 架构概览

```
                 ┌──────────────────────────┐
                 │  API endpoint            │
                 │  (user request → session) │
                 └──────┬───────────────────┘
                        │ 传入 session_id
                        ▼
                 ┌──────────────────────┐
                 │  chat_with_tools()   │
                 │  (AgentService)      │
                 │   +session_id 参数   │
                 └──────┬───────────────┘
                        │ 完成后异步触发 (fire-and-forget)
                        ▼
                 ┌──────────────────────┐
                 │  SummaryService      │
                 │  1. LLM 摘要生成     │
                 │  2. PG 持久化        │
                 │  3. Qdrant 向量化    │
                 └──────┬───────────────┘
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
     ┌──────────┐ ┌──────────┐ ┌──────────┐
     │PostgreSQL│ │  Qdrant  │ │  Redis   │
     │持久化    │ │向量检索  │ │缓存(可选)│
     └──────────┘ └──────────┘ └──────────┘
            │
            ▼
     ┌──────────┐
     │  前端    │
     │记忆管理UI│
     └──────────┘
```

### 决策说明

| 决策点 | 选择 | 理由 |
|:---|:---|:---|
| 存储引擎 | PostgreSQL + Qdrant | 结构化元数据用 PG，语义检索用 Qdrant（已有 Docker 部署）|
| 检索策略 | Qdrant 纯向量 | 放弃 FTS（`simple` 配置不支持中文分词；`zhparser` 引入成本 > 收益）|
| 摘要时机 | `chat_with_tools()` 返回后异步 | 不阻塞主对话，后台 fire-and-forget |
| 注入方式 | 新会话 system prompt 追加 | 最小侵入，Agent 无需改造 |
| session 去重 | 同 session_id 覆盖更新 | 避免同一会话生成 N 条重复摘要 |
| session_id 来源 | API 层生成并透传 | 用户首次请求时生成 UUID，后续复用 |

---

## 3. 数据库设计

### 3.1 `session_summaries` 表（PostgreSQL）

```sql
CREATE TABLE session_summaries (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id   VARCHAR(255) NOT NULL,
    title        VARCHAR(255) NOT NULL DEFAULT '',
    summary_text TEXT NOT NULL,
    key_insights JSONB NOT NULL DEFAULT '[]',
    tool_patterns JSONB NOT NULL DEFAULT '[]',
    metadata     JSONB NOT NULL DEFAULT '{}',
    vectorized   BOOLEAN NOT NULL DEFAULT FALSE,   -- Qdrant 是否写入成功
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 索引（B-tree，不设 BRIN；数据量达到百万级后再评估）
CREATE INDEX idx_summaries_user_id ON session_summaries(user_id);
CREATE INDEX idx_summaries_session_id ON session_summaries(session_id);
CREATE INDEX idx_summaries_created_at ON session_summaries(created_at DESC);
CREATE UNIQUE INDEX idx_summaries_user_session ON session_summaries(user_id, session_id);
```

> **注意**：`UNIQUE(user_id, session_id)` 确保同一 session 只有一条摘要。摘要生成采用 **upsert 语义**：同一 session_id 第二次调用时执行 UPDATE，不 INSERT。

### 3.2 key_insights JSONB 结构

```json
[
    {
        "type": "preference",
        "content": "用户偏好 Java 后端候选人，3 年以上经验",
        "confidence": 0.85,
        "source_session": "session_xxx"
    }
]
```

`type` 可选值：`preference` / `filter_condition` / `rejection_reason` / `success_pattern` / `tool_usage`

### 3.3 Qdrant 集合

- **集合名**: `session_summaries`
- **向量维度**: 运行时自动检测（从 `embed()` 返回值长度推断；config 中不硬编码）
- **Payload**: `{id, user_id, title, created_at}`
- **距离度量**: Cosine
- **索引**: HNSW（ef_construct=200, M=32）

---

## 4. 服务层设计

### 4.1 SummaryService

```python
class SummaryService:
    """会话摘要服务 — LLM 摘要生成 + PG 持久化 + Qdrant 向量化"""

    async def generate_and_store(
        self, user_id: str, session_id: str,
        messages: list[dict], tool_calls: list[dict]
    ) -> Summary | None:
        """三步：LLM 摘要 → PG upsert → Qdrant 向量化
           任何一步失败都不阻塞后续步骤。
           同 session_id 重复调用 = 更新已有摘要。
        """

    async def get_user_summaries(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[Summary], int]:
        """分页获取用户的摘要列表（按 created_at DESC），前端做搜索过滤"""

    async def get_by_id(self, summary_id: str) -> Summary | None:
        """单条摘要详情"""

    async def search_similar(
        self, user_id: str, query_embedding: list[float],
        top_k: int = 5, score_threshold: float = 0.6
    ) -> list[Summary]:
        """Qdrant 向量相似度检索，支持 user_id 过滤"""

    async def search_fallback(
        self, user_id: str, top_k: int = 5
    ) -> list[Summary]:
        """降级策略：Qdrant 不可用时按时间倒序取最近 top_k 条"""

    async def delete(self, summary_id: str) -> bool:
        """删除摘要（PG + Qdrant 联动）"""

    async def update(
        self, summary_id: str,
        title: str | None = None,
        summary_text: str | None = None,
        key_insights: list | None = None,
    ) -> Summary | None:
        """编辑摘要（用户手动编辑；编辑后 PG 更新 + Qdrant 重新向量化）"""

    async def get_or_create_for_session(
        self, user_id: str, session_id: str
    ) -> Summary:
        """按 user_id + session_id 查找已有摘要，找到则返回，否则创建空占位"""
```

### 4.2 LLM 摘要 Prompt

```
你是一个招聘助手的会话摘要专家。请根据以下对话内容，
生成一份结构化的会话摘要。

要求：
1. title: 简短标题（10 字以内），概括会话主题
2. summary_text: 200 字以内的摘要正文
3. key_insights: 提取关键洞察，每条包含 type 和 content
   - type 可选值：preference（用户偏好）、filter_condition（筛选条件）、
     rejection_reason（拒绝原因）、success_pattern（成功模式）、tool_usage（工具使用）
   - content 是具体的洞察描述

对话消息：
{messages}

工具调用记录：
{tool_calls}

请严格按以下 JSON 格式返回（不要包含其他文字）：
{
  "title": "...",
  "summary_text": "...",
  "key_insights": [
    {"type": "preference", "content": "...", "confidence": 0.9},
    ...
  ],
  "tool_patterns": ["tool_name_1", "tool_name_2"]
}
```

### 4.3 加权检索策略

```
最终得分 = 向量相似度 × time_decay

time_decay = 1.0 / (1.0 + 0.1 * days_since_creation)
  → 创建 1 天内: 0.99
  → 30 天: 0.25
  → 90 天: 0.10
```

检索返回 Top N 条后按最终得分排序取前 k 条。

### 4.4 Token 预算控制

注入 system prompt 的记忆上下文有 token 预算限制：

```python
MAX_MEMORY_TOKENS = 1500      # 记忆上下文 token 预算上限
retrieved = search_similar(...)
# 从高到低排序，累积 tokens 不超过预算
```

超过预算的部分舍弃。仍低于预算时（如新用户无记忆），不追加内容。

### 4.5 Agent prompt 注入

每次 `chat_with_tools()` 被调用时：

1. 取 `messages[-1]`（用户最新一条消息）作为 query，调用 `llm.embed()` 生成 query vector
2. 调用 `QdrantService.search()` 检索相似记忆（按最终得分排序 + token 预算截断）
3. 如果检索结果与上次检索的 top-1 记忆 `id` 相同且相似度 > 0.95 → **跳过本次注入**（避免重复注入相同内容）
4. 在 `SYSTEM_PROMPT` 尾部追加：

```
以下是你之前了解到的用户偏好和历史信息（基于相似度检索）：
{retrieved_summaries}
```

5. 记录日志：

```python
logger.info(
    "Memory context injected: user=%s session=%s count=%d tokens=%d",
    user_id, session_id, len(retrieved), total_tokens,
)
```

---

## 5. session_id 生命周期

| 阶段 | 动作 | 责任方 |
|:---|:---|:---|
| 用户首次请求 | API endpoint 生成 `uuid4` 作为 `session_id`，返回给前端 | 后端 API |
| 后续请求 | 前端在请求头或 body 中携带 `session_id` | 前端 |
| 无活动 > 30 分钟 | 前端生成新的 `session_id`（视为新会话） | 前端 |
| 用户主动"新会话" | 前端重新生成 `session_id` | 前端 |
| 后端接收 | `chat_with_tools()` 接收可选参数 `session_id: str \| None`，`None` 时自动生成 | AgentService |

**影响**：前端现用 API client（`apps/web/lib/trpc.ts`）需要在首次请求后存储返回的 `session_id`，后续请求附带。

---

## 6. API 设计

### 6.1 新增端点

| 方法 | 路径 | 说明 | 认证 |
|:---|:---|:---|:---:|
| `GET` | `/api/v1/memory/summaries` | 分页获取当前用户的摘要列表 | 需要 |
| `GET` | `/api/v1/memory/summaries/{id}` | 单条摘要详情 | 需要 |
| `PUT` | `/api/v1/memory/summaries/{id}` | 编辑摘要 | 需要 |
| `DELETE` | `/api/v1/memory/summaries/{id}` | 删除摘要 | 需要 |

> **无 search 端点**：前端拉取列表后本地 `Array.filter()` 搜索。
> **无 session 级端点**：session 写入是服务端内部的，不暴露给用户直接操作。

### 6.2 响应格式

沿用已有 `core/response.py` 的统一格式：

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "title": "Java 后端候选人初筛",
    "summary_text": "...",
    "key_insights": [...],
    "tool_patterns": [...],
    "created_at": "2025-06-01T10:00:00Z",
    "updated_at": "2025-06-01T10:00:00Z"
  }
}
```

分页列表：
```json
{
  "success": true,
  "data": [...],
  "total": 42,
  "skip": 0,
  "limit": 20
}
```

---

## 7. 前端 UI 设计

### 7.1 Settings 页面增加"记忆管理" Tab

在现有 `apps/web/app/(dashboard)/settings/page.tsx` 中新增 tab 切换：

**Tab 1**: 系统设置（现有内容）
**Tab 2**: 记忆管理（新增）

### 7.2 记忆管理 UI 结构

```
┌──────────────────────────────────────────────┐
│  系统设置  |  记忆管理                        │  ← Tab
├──────────────────────────────────────────────┤
│  🔍 [搜索框: 前端过滤]                        │
│                                               │
│  ┌────────────────────────────────────────┐   │
│  │ 📋 Java 后端候选人初筛                  │   │
│  │ 2025-06-01 · 3 条洞察                  │   │
│  │ [编辑] [删除]                          │   │
│  ├────────────────────────────────────────┤   │
│  │ 🔍 React前端人才搜索                   │   │
│  │ 2025-05-28 · 2 条洞察                  │   │
│  │ [编辑] [删除]                          │   │
│  └────────────────────────────────────────┘   │
│                                               │
│  编辑弹窗:                                    │
│  ┌────────────────────────────────────────┐   │
│  │ 编辑记忆                               │   │
│  │ 标题: [________________]               │   │
│  │ 摘要: [textarea]                       │   │
│  │ 洞察: [列表可编辑]                     │   │
│  │ [保存] [取消]                          │   │
│  └────────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

### 7.3 状态覆盖

| 状态 | 表现 |
|:---|:---|
| **Loading** | 骨架屏（每个卡片灰色脉冲） |
| **Empty** | "暂无记忆，开始使用 AI 招聘助手后将会自动记录" |
| **Error** | Toast 提示 + 重试按钮 |
| **Delete** | 确认弹窗"确定删除此记忆？删除后无法恢复" |

---

## 8. 数据库迁移计划

### 文件：`apps/api/alembic/versions/xxxx_add_session_summaries.py`

```python
"""add session_summaries table

Revision ID: xxxx
Create Date: 2025-05-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'xxxx'
down_revision = 'fe85e4504f2b'

def upgrade():
    op.create_table(
        'session_summaries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('title', sa.String(255), server_default=''),
        sa.Column('summary_text', sa.Text, nullable=False),
        sa.Column('key_insights', postgresql.JSONB, server_default='[]'),
        sa.Column('tool_patterns', postgresql.JSONB, server_default='[]'),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('vectorized', sa.Boolean, server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_summaries_user_id', 'session_summaries', ['user_id'])
    op.create_index('idx_summaries_session_id', 'session_summaries', ['session_id'])
    op.create_index('idx_summaries_created_at', 'session_summaries', ['created_at'])
    op.create_unique_constraint('uq_summaries_user_session', 'session_summaries', ['user_id', 'session_id'])

def downgrade():
    op.drop_table('session_summaries')
```

---

## 9. Qdrant 集成方案

### 9.1 新增依赖

```
qdrant-client>=1.12.0
```

### 9.2 QdrantService（新建）

```python
class QdrantService:
    """Qdrant 向量检索服务"""

    def __init__(self):
        from qdrant_client import AsyncQdrantClient
        from app.core.config import settings
        # 用 url 参数，不使用已弃用的 host/port 构造
        self.client = AsyncQdrantClient(
            url=f"http://{settings.qdrant_host}:{settings.qdrant_port}",
        )
        self.collection_name = "session_summaries"
        self._vector_size: int | None = None

    async def ensure_collection(self, vector_size: int | None = None):
        """确保集合存在，不存在则创建。
        如果 vector_size 不传，从第一次 embedding 结果自动检测。
        """

    async def upsert(self, point_id: str, vector: list[float], payload: dict):
        """写入向量点"""

    async def search(
        self, vector: list[float], top_k: int = 5,
        score_threshold: float = 0.6,
        user_id: str | None = None
    ) -> list[ScoredPoint]:
        """向量检索，支持按 user_id 过滤"""
        filter_ = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ) if user_id else None
        ...

    async def delete(self, point_id: str):
        """删除向量点（联动 PG 删除时调用）"""

    async def health_check(self) -> bool:
        """检查 Qdrant 是否可用"""
```

### 9.3 config.py 新增字段

```python
# Qdrant 配置
qdrant_host: str = "localhost"
qdrant_port: int = 6333
# 注意：不用 grpc_port；本地 Docker 开发环境默认不启用 gRPC
```

---

## 10. 错误处理与降级

| 场景 | 行为 | 影响 | 可恢复？|
|:---|:---|:---|:---:|
| LLM 摘要生成失败 | 跳过摘要，记录 warning | 本次会话无摘要 | 下次会话重试 |
| PG 写入失败 | 记录 error，不阻塞主流程 | 本次无摘要 | 下次会话重试 |
| Embedding 失败 | 捕获异常，标记 `vectorized=false` | Qdrant 不写入 | 下次会话重试 |
| Qdrant 写入失败 | 标记 `vectorized=false`，PG 数据已存 | 检索降级 | 后续会话重试向量化 |
| Qdrant 检索失败/超时 | 调用 `search_fallback()` 按时间倒序取最近 5 条 | 检索精度下降，可用性不受影响 | 下次检索重试 |
| Qdrant 整体不可用 | `health_check()` 返回 False → 跳过所有 Qdrant 操作 | 全量降级为时间倒序 | — |

---

## 11. 测试策略

### 11.1 测试文件

新建 `apps/api/tests/test_summary_service.py`（覆盖 SummaryService）

### 11.2 Mock 方案

| 依赖 | Mock 方法 |
|:---|:---|
| LLM `.chat()` | `unittest.mock.patch` 返回固定 JSON 字符串 |
| LLM `.embed()` | `unittest.mock.patch` 返回固定长度 float 数组 |
| Qdrant `AsyncQdrantClient` | `unittest.mock.AsyncMock` 模拟 search/upsert/delete |
| DB `AsyncSession` | 使用 `pytest-asyncio` + SQLAlchemy `AsyncSessionLocal`（真实测试数据库） |

### 11.3 测试用例

| # | 用例 | 类型 |
|:---|:---|:---|
| 1 | `generate_and_store` 正常路径：LLM 返回有效 JSON → PG 写入成功 → Qdrant 写入成功 | 集成 |
| 2 | LLM 返回非法 JSON → 降级处理，不崩溃 | 异常 |
| 3 | LLM 抛异常 → 跳过摘要生产，不阻塞 | 异常 |
| 4 | Qdrant 不可用 → PG 写入成功，`vectorized=false` | 降级 |
| 5 | 同 `session_id` 第二次调用 → 更新已有摘要（不新增行）| 幂等 |
| 6 | `search_fallback()` → Qdrant 不可用时返回时间倒序结果 | 降级 |
| 7 | `delete()` → PG 删除 + Qdrant 联动删除 | 集成 |
| 8 | `update()` → PG 更新 + Qdrant 重新向量化 | 集成 |

### 11.4 覆盖率目标

- `SummaryService`: ≥ 80%
- `QdrantService`: ≥ 70%（mock Qdrant 依赖）

---

## 12. 退出检查清单

```
[ ] pytest 全部通过（含新增 summary_service 测试）
[ ] pnpm build 通过
[ ] 会话结束后 session_summaries 表写入数据（psql 查表确认）
[ ] 同一 session 多次对话不重复创建摘要行（唯一约束验证）
[ ] 新会话 system prompt 中包含历史摘要（日志行 "Memory context injected" 可查）
[ ] Qdrant 集合中存在向量数据（Qdrant REST API: GET /collections/session_summaries）
[ ] Settings 页面"记忆管理" tab 可查看/搜索/删除记忆
[ ] Qdrant 不可用时检索降级为按时间倒序取最近 5 条
[ ] SummaryService 覆盖率 ≥ 80%，QdrantService 覆盖率 ≥ 70%
```

---

## 13. 工作量估计

| 项目 | 预估 | 并行 |
|:---|:---|:---:|
| DB migration + SQLAlchemy Model | 1h | — |
| QdrantService | 1h | ✅ 与 migration 并行 |
| SummaryService（摘要生成 + 持久化 + 检索）| 2h | 依赖 migration |
| chat_with_tools() hook（session_id + 检索注入）| 1h | 依赖 SummaryService |
| API routes（list/detail/update/delete）| 0.5h | ✅ 与前端并行 |
| 前端记忆管理 UI（tab + 列表 + 编辑弹窗）| 2h | ✅ 与后端并行 |
| 测试（summary + qdrant 覆盖）| 1h | — |
| **合计** | **~8.5h** | |

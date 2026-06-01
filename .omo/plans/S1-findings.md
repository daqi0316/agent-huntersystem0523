# S.1 关键发现 — LangGraph Checkpoint 集成

> 2026-06-01 S.1 验证结果

## 安装结果

| 包 | 版本 | 用途 |
|---|---|---|
| `langgraph` | 0.2.76 | StateGraph / END / NodeInterrupt |
| `langgraph-checkpoint-postgres` | 2.0.25 | PostgresSaver / AsyncPostgresSaver |
| `langgraph-checkpoint` | 2.1.2 | MemorySaver（默认）|
| `psycopg[binary]` | 3.3.4 | psycopg3 连接（langgraph 强制依赖）|
| `pydantic[email]` | 2.x | EmailStr 支持（修 conftest 收集错误）|
| `beautifulsoup4` | 4.14.3 | app/skills/web_search/skill.py（修 conftest 收集错误）|

`pytest --collect-only` ✅ **1382 tests collected, 0 errors** — Phase R gate 通过。

## 关键发现（必须看）

**`langgraph-checkpoint-postgres` 用 psycopg3，NOT asyncpg。**

```
PostgresSaver.__init__(self, conn: '_internal.Conn', ...)
                       ^^^^^^^^^^^^^^^^^^^^^^^^
                       psycopg3 Connection
AsyncPostgresSaver.__init__(self, conn: '_ainternal.Conn', ...)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                          psycopg3 AsyncConnection
```

我们现有的 SQLAlchemy 走的是 `asyncpg` 驱动 (`postgresql+asyncpg://...`)。**这两个是独立的连接池**。

### 集成方案（给 S.4 任务管理 API 用）

```python
# apps/api/app/core/checkpointer.py  (S.4 落地)
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

@asynccontextmanager
async def get_checkpointer():
    pool = AsyncConnectionPool(
        conninfo=settings.LANGGRAPH_PG_DSN,  # 独立 DSN,无 SQLAlchemy
        min_size=1, max_size=10, kwargs={"autocommit": True},
    )
    async with pool.connection() as conn:
        saver = AsyncPostgresSaver(conn)
        await saver.setup()  # 一次性建表
        yield saver
```

需要新增配置项：
- `LANGGRAPH_PG_DSN` — 独立于 SQLALCHEMY_DATABASE_URI 的连接串
- 生产环境可同库不同 schema（或独立库以隔离 LangGraph state）

### 降级方案

如果 PostgresSaver + 现有 asyncpg 基础设施冲突：
- **Phase S 早期用 MemorySaver**（已写在 `orchestrator_graph.py:145`）
- 仅在生产部署前切到 PostgresSaver
- 短期：completed run 持久化到 `operation_log` 表（已有）+ 内存 checkpoint

## 给 S.2-S.8 的提示

- `orchestrator_graph.py` 已是完整 StateGraph，9 节点 + 1 conditional edge
- `resume_parser_graph.py` 7 节点 + 1 conditional edge，**quality / risk / dedup 是 placeholder**（S.2 任务）
- `_INTENT_TO_NODE` 已覆盖全部 7 个 intent
- 9 个 execute_* 节点全部走 `AgentRegistry.resolve(agent_type).run(...)`
- 既有 `app/agents/orchestrator_agent.py` + `orchestrator_session.py` 仍在用（S.6 删）

## 退出标准

- [x] `langgraph` + `langgraph-checkpoint-postgres` 装好
- [x] `pytest --collect-only` 1382/1382 通过
- [x] PostgresSaver API 验证（知道要 psycopg3）
- [ ] S.4 落地前建 `LANGGRAPH_PG_DSN` 配置项

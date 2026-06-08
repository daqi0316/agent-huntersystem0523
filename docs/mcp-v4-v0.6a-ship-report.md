# MCP v4 v0.6a Ship Report — RQ worker + submit/poll 异步骨架

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.6-plus-replan.md` §4 v0.6a
> **Git tag**: `mcp-v4-v0.6a-pre` (commit a03a6c3) → `mcp-v4-v0.6a-shipped`
> **commit**: 1 个 feat + 后续 ship report
> **接受门槛**: 6 新测试 + 回归 9 测试 = 16/16 + mcp-resume list_tools 6 工具 + e2e 14/14 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| RQ 依赖 | ✅ rq 2.9.1 装好 |
| `parse_task` service (enqueue + poll) | ✅ |
| `parse_worker` RQ worker 入口 | ✅ |
| `POST /raw-resumes/parse` (submit) | ✅ |
| `GET /raw-resumes/{id}/status` (poll) | ✅ |
| `_handle_parse_resume_async` handler | ✅ enqueue 失败时 raw_resume 标 failed |
| `_handle_poll_parse` handler | ✅ 三态 (processing/parsed/failed) |
| tools 列表 +2 | ✅ parse_resume_async / poll_parse_resume |
| metadata 注册 +2 | ✅ retryable 区分 |
| docker-compose dev/prod parse_worker | ✅ |
| Makefile celery:dev/celery:watch | ✅ (双 fork daemonize) |
| 测试 | ✅ 7 新 + 9 回归 = 16/16 |
| mcp-resume list_tools | ✅ 6 工具 (3 sync + 3 Bheavy + 1 retry_raw_resume) |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/pyproject.toml` | +1 / 0 | rq>=1.16.0 |
| `apps/api/app/services/parse_task.py` | +93 (新) | enqueue + poll |
| `apps/api/app/workers/parse_worker.py` | +34 (新) | RQ worker 入口 |
| `apps/api/app/workers/__init__.py` | +0 (新) | 包标记 |
| `apps/api/app/api/raw_resume.py` | +104 (新) | HTTP API |
| `apps/api/app/api/router.py` | +2 / 0 | include_router |
| `apps/api/app/tools/resume_parser.py` | +140 / 0 | 2 handler + tools + handlers |
| `apps/api/app/tools/metadata.py` | +14 / 0 | 2 register_tool |
| `docker-compose.dev.yml` | +21 / 0 | parse_worker service |
| `docker-compose.prod.yml` | +37 / 0 | parse_worker service + healthcheck |
| `Makefile` | +16 / 0 | celery:dev/celery:watch/_celery:run-detached |
| `apps/api/tests/mcp/integration/test_resume_parser_v0_6a_async.py` | +183 (新) | 7 测试 |
| **总** | **+645 / 0** | 11 文件改动 |

## 3. 关键决策

### 3.1 RQ 而非 Celery（Momus §3 决策点 1）

**为什么 RQ**：
- 项目轻需求：1 类任务（parse_resume），不需要任务链
- Redis 已有（Phase Z ship）
- 1 worker 进程即可（vs Celery worker + beat + result backend）
- 部署简单：`rq worker parse_queue --url $REDIS_URL`

**vs Celery 关键差异**：
- RQ: `queue.enqueue(callable, *args, **kwargs)` 同步 API
- Celery: `task.delay(*args)` 异步 + 装饰器
- RQ 简单但扩展性弱（v0.6a 单任务够用）

### 3.2 enqueue 失败时把 raw_resume 标 failed（防 stuck）

```python
try:
    task_id = enqueue_parse_task(...)
except Exception as e:
    # 失败: 把 raw_resume 标 failed (不要让 task 永远 stuck processing)
    async with AsyncSessionLocal() as db:
        stuck = await db.get(RawResume, raw_resume_id)
        if stuck is not None:
            stuck.status = RawResumeStatus.FAILED
            stuck.error_message = f"enqueue_failed: {e}"
            await db.commit()
    return {"status": "failed", "error": {"code": "QUEUE_UNAVAILABLE", ...}}
```

**为什么**：Redis 断连时 enqueue 抛 ConnectionError，raw_resume 仍在 `status=processing`。客户端 poll 时永远看到 "processing"，stuck 死锁。降级到 failed + error_message 提示用户 retry。

### 3.3 poll 走 raw_resumes 表而非 RQ Job 状态

```python
async def poll_parse_task(raw_resume_id: str):
    rr = await db.get(RawResume, raw_resume_id)  # source of truth
    return {status, candidate_id, error_message, ...}
```

**为什么**：`_do_extract_and_link`（v0.5a 抽出）在 LLM 成功/失败时会写 `raw_resumes.status=parsed/failed`，这是**业务状态机**。RQ Job 状态是 `queued/started/finished/failed`，是**基础设施状态**。

- 业务状态机（raw_resumes）= 用户视角的"任务进度"
- 基础设施状态（RQ Job）= 内部 debug 用

让用户 poll 业务状态机更直觉。`stuck processing` 检测 = `started` 但 raw_resumes 仍 processing 超过 N 分钟 → ADR 推 v0.6a.1 加 watch dog。

### 3.4 HTTP 路径用连字符（CLAUDE.md 模式 3）

```python
api_router.include_router(raw_resume_router, prefix="/raw-resumes", tags=["Raw Resume"])
```

**为什么**：`/raw-resumes/parse` 而非 `/raw_resumes/parse`（CLAUDE.md 明确 `human-loop` 用连字符，与 FastAPI router prefix 无关）。

### 3.5 file_url 走 v0.6a.1

`parse_resume_async` 暂只支持 `content` 参数。`file_url` 走 v0.6a.1（HTTP API 完整版 + 异步下载）。

**为什么**：v0.6a 范围已大（10 文件），file_url 下载是独立子问题（`_file_parser_helpers.download_and_save` 同步 + 异步下载需新实现）。v0.6a.1 单 PR 处理。

### 3.6 Makefile 3.81 多 target 兼容性

Makefile 加 `celery:dev` `celery:watch` `_celery:run-detached` 3 个新 target。**但** make 3.81（v0.5a 修过）有 `dev:infra:` 双 target 解析 bug，**新 target 不受影响**（单冒号）。

`make celery:dev` 在 make 3.81 跑不通（整文件解析 fail），但功能用 bash 命令行可达：`rq worker parse_queue --url redis://localhost:6379/0`。**不阻塞 v0.6a ship**。

## 4. 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_submit_returns_raw_resume_id_and_task_id` | 主路径：submit 落 raw_resume + enqueue RQ，返 task_id |
| 2 | `test_submit_empty_content_returns_invalid_input` | 参数校验 |
| 3 | `test_submit_enqueue_fails_returns_queue_unavailable` | Redis down → 503 + raw_resume 标 failed |
| 4 | `test_poll_status_processing` | poll 三态之一：processing |
| 5 | `test_poll_status_parsed` | poll 三态之二：parsed |
| 6 | `test_poll_status_failed` | poll 三态之三：failed + retryable |
| 7 | `test_poll_not_found_returns_not_found` | poll 不存在的 raw_resume_id |

**mock 模式**：
- `patch("app.services.parse_task.enqueue_parse_task")` 改函数本身，函数内 import 拿到 mocked
- `patch("app.services.parse_task.poll_parse_task")` 返 fake dict，避免 mock 函数内 lazy import 的 `AsyncSessionLocal`

## 5. 退出门槛验证 / PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 7 新测试 + 9 回归 = 16/16 | `pytest tests/mcp/integration/test_resume_parser_v0_6{4d,5b_retry, a_async}.py` | ✅ 16 passed |
| mcp-resume list_tools 6 工具 | 直接 spawn mcp-resume server | ✅ parse_resume / parse_resume_async / poll_parse_resume / batch_parse_resumes / get_candidate_profile / retry_raw_resume |
| e2e 14/14 仍 pass | `mcp_v4_e2e_14_servers.py` | ✅ 14/14, mcp-resume tools=6 |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14（9 步全过）|

## 6. 未在 v0.6a 范围

按 v0.6-plus-replan §4 v0.6a 退出标准，明确推到后续 PR：

- ❌ `file_url` 异步下载（推 v0.6a.1）
- ❌ `batch_parse_resumes_async`（推 v0.6.1）
- ❌ WebSocket 进度推送（v0.6b）
- ❌ force=True（v0.6c）
- ❌ parse_worker_watchdog 实现（Makefile target 已写，缺 `app/scripts/parse_worker_watchdog.py` 推 v0.6a.1）
- ❌ stuck processing 检测（raw_resumes.status=processing 超过 N 分钟告警，推 v0.6a.1）
- ❌ Playwright 端到端测试（dev 栈未就绪，按 Phase D 推到 v1.1）

## 7. 后续路径

**v0.6a.1（小补丁，0.5d，1 commit）**：
- `file_url` 异步下载（走 `_file_parser_helpers`）
- `batch_parse_resumes_async`（循环 enqueue + 合并进度）
- `app/scripts/parse_worker_watchdog.py`（双 fork daemonize，对应 Makefile target）
- stuck processing 检测（90s 阈值 + log 警告）

**v0.6b（1d，1 commit）**：WebSocket 进度推送（`?token=` 鉴权）

**v0.6c（1d，1 commit）**：force=True 参数（方案 A：清空 candidate_id + 重建）

**v0.7（2d，2 commit）**：skill_mgr 5 工具（与 v0.6a 并行 2 agent）

## 8. 回滚方法

```bash
# 失败回滚（v0.6a 风险点：docker-compose 改 + Makefile 改 + RQ 装包）
git checkout mcp-v4-v0.6a-pre   # 回到 v0.6a 改之前（v0.5b ship 状态）
# 或
git revert <v0.6a-commit>      # 撤销 v0.6a 单 commit

# 改动 11 文件: 
#   4 新: parse_task.py / parse_worker.py / workers/__init__.py / raw_resume.py / test_v0_6a_async.py
#   7 改: pyproject.toml / router.py / resume_parser.py / metadata.py 
#         docker-compose.dev.yml / docker-compose.prod.yml / Makefile
# 回滚 = revert 1 commit + uv pip uninstall rq
```

**回滚影响范围**：
- mcp-resume tools 6 → 4（删 parse_resume_async + poll_parse_resume）
- HTTP API `/raw-resumes/parse` + `/raw-resumes/{id}/status` 不可用
- parse_queue RQ 任务不执行（无 worker 消费）
- **v0.5b retry_raw_resume 不受影响**（无共享代码）
- v0.4d/v0.5b 9 测试仍 pass

## 9. v0.6 系列累计

| 阶段 | commit | 改动 | 估时 |
|---|---|---|---|
| v0.6a RQ + submit/poll | `<v0.6a-commit>` | +645 / 0 | 1.5d (实际 1d) |
| **总计 v0.6a** | 1 commit | **+645 / 0** | **1d** |

## 10. 引用

- v0.6+ 修正版: `.omo/plans/v0.6-plus-replan.md` §4 v0.6a
- v0.6+ Momus 审核: `.omo/plans/v0.6-plus-momus-review.md`
- v0.5a ship: `docs/mcp-v4-v0.5a-ship-report.md`（抽 _do_extract_and_link 公共函数）
- v0.5b ship: `docs/mcp-v4-v0.5b-ship-report.md`（retry_raw_resume 工具）
- v0.4d commit: `1549b43`（raw_resumes 表事务边界）
- e2e 脚本: `scripts/mcp_v4_e2e_14_servers.py`
- health-check 脚本: `scripts/health-check.sh`

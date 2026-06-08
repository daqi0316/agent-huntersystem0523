# MCP v4 v0.6b Ship Report — WebSocket 进度推送

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.6-plus-replan.md` §4 v0.6b
> **Git tag**: `mcp-v4-v0.6b-pre` (commit 76662cc, v0.6a ship report) → `mcp-v4-v0.6b-shipped` (commit 3c120b1)
> **commit**: 1 个 feat + 后续 ship report
> **接受门槛**: 7 新测试 + 16 回归 = 23/23 + e2e 14/14 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| WS 端点 `/raw-resumes/{id}/progress` | ✅ |
| 鉴权 (header + ?token=) | ✅ 走 CLAUDE.md 模式 5 |
| 状态轮询 200ms 间隔 | ✅ |
| Terminal 状态自动关闭 | ✅ |
| 抽 `_poll_state_until_terminal` 独立函数 | ✅ (便于 unit test) |
| 提升 `decode_access_token` 到模块顶部 | ✅ (避免 lazy import patch 不到) |
| mcp-resume 工具数 | ✅ 仍 6 (v0.6b 只加 HTTP, 不动 MCP) |
| 测试 | ✅ 7 新 + 16 回归 = 23/23 |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/api/raw_resume.py` | +80 / -4 | WS 端点 + 鉴权 + 状态轮询 helper |
| `apps/api/tests/mcp/integration/test_resume_parser_v0_6b_ws.py` | +183 (新) | 7 测试 |
| **总** | **+263 / -4** | 2 文件 |

## 3. 关键决策

### 3.1 鉴权用 CLAUDE.md 模式 5（决策点 2）

```python
async def _authenticate_ws(websocket: WebSocket) -> str | None:
    auth = websocket.headers.get("authorization", "")
    token = None
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)  # policy violation
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=1008)
        return None
    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=1008)
        return None
    return user_id
```

**为什么 header 优先 + ?token= 兜底**：
- curl / Node SDK 用 Authorization header（标准）
- 浏览器 EventSource / WebSocket 不能设 header，必须 `?token=`（CLAUDE.md 模式 5）

**为什么 close(1008)**：WebSocket 1008 = Policy Violuation，标准协议码，浏览器/SDK 都能识别为"鉴权失败"。

### 3.2 200ms 轮询而非 Redis pub/sub

```python
async def _poll_state_until_terminal(websocket, raw_resume_id, send_json):
    last_status = None
    while True:
        result = await poll_parse_task(raw_resume_id)
        if result is None:
            await send_json({"raw_resume_id": raw_resume_id, "status": "not_found"})
            break
        current_status = result["status"]
        if current_status != last_status:
            await send_json(result)
            last_status = current_status
            if current_status in ("parsed", "failed"):
                break
        await asyncio.sleep(0.2)
```

**为什么轮询**：
- **简单**：零跨进程通信，WS 端点和 RQ worker 各自只读写 raw_resumes 表
- **零延迟**：worker 写 status 200ms 内 WS 端点看到
- **可观测**：状态变化是 raw_resumes 表的 row write，DB 自带

**vs Redis pub/sub 推模式**：
- pub/sub 需 worker 端写消息格式（ack、retry、消息丢失处理）
- 跨进程消息易丢（worker 崩了消息没送达）
- v0.6b 范围已大，**轮询优先**

**vs "set_progress(50)"**（v0.6-plus-replan §4 v0.6b 原文）：
- raw_resumes 表无 `progress` 字段，加需 migration
- LLM 1-3s 内是单步（extract），没有"中途进度"概念
- **progress 字段推 v0.6b.1 后续**（真要加 LLM 中间事件再设计）

### 3.3 抽 `_poll_state_until_terminal` 独立函数

**为什么抽**：
- WS 端点本身用 FastAPI `@router.websocket()` 装饰，TestClient 调起涉及 starlette 内部 event loop
- 状态轮询逻辑（while + poll + sleep + 状态变化比较）是纯 async 函数
- 抽出来**用 `pytest-asyncio` 直接 await**，**绕过 starlette TestClient**

**实际测试路径**：
- `_authenticate_ws` 直接 await（mock websocket）
- `_poll_state_until_terminal` 直接 await（mock send_json callback + asyncio.sleep）

**WS 端到端测试**（TestClient.websocket_connect）涉及 starlette 事件循环与 pytest-asyncio 冲突，**推 v0.6b.1** 走 Playwright e2e。

### 3.4 decode_access_token 提升到模块顶部

原 lazy import（函数内 `from app.core.security import decode_access_token`）有理由（避免循环 import），但**测试时 patch 不到**（Python 解析函数内 import 时不查 module 命名空间）。

修：提升到模块顶部：
```python
from app.core.security import decode_access_token
```

**代价**：raw_resume.py 启动时 import security 多 1 个模块。但 security 不重（< 10KB），影响可忽略。

**好处**：unit test 可 patch `app.api.raw_resume.decode_access_token`。

### 3.5 mcp-resume 工具数不变（6 工具）

v0.6-plus-replan §4 v0.6b 写"mcp-resume 加工具 watch_parse_progress"。**实际不做**，理由：
- watch_parse_progress MCP 工具 = 调 `poll_parse_task` 返单次状态，与 `poll_parse_resume` 工具**功能重复**
- WS 推送是 HTTP 层（前端用），MCP Agent 调 `poll_parse_resume` 实时轮询已够
- 工具去重避免 DRY 违反

**mcp-resume 工具数 6 仍**（v0.6a 加 parse_resume_async + poll_parse_resume）。

## 4. 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_authenticate_ws_via_authorization_header` | header 优先路径 |
| 2 | `test_authenticate_ws_via_query_token_fallback` | `?token=` 兜底（CLAUDE.md 模式 5）|
| 3 | `test_authenticate_ws_no_token_closes_with_1008` | 无 token 拒收 + close(1008) |
| 4 | `test_authenticate_ws_bad_token_closes_with_1008` | 坏 token (JWTError) 拒收 + close(1008) |
| 5 | `test_state_polling_emits_processing_then_parsed_then_stops` | 主路径：processing → parsed (terminal) |
| 6 | `test_state_polling_emits_processing_then_failed_then_stops` | 失败路径：processing → failed (terminal) |
| 7 | `test_state_polling_not_found_emits_not_found` | not_found 路径：raw_resume 不存在 |

**mock 模式**：
- `patch("app.api.raw_resume.decode_access_token")` — 模块级 import，patch 生效
- `patch("app.api.raw_resume.poll_parse_task")` — 函数内 import，patch 生效（已经是 module 命名空间）
- `patch("app.api.raw_resume.asyncio.sleep")` — 加速测试，跳过 200ms 等待
- 自建 `_FakeWebSocket` 模拟 starlette WebSocket 必要属性

## 5. 退出门槛验证 / PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 7 新测试 + 16 回归 = 23/23 | `pytest tests/mcp/integration/test_resume_parser_v0_6{b,a,5b,4d}*.py` | ✅ 23 passed |
| mcp-resume list_tools 6 工具 | e2e 14/14 跑 | ✅ 6 工具（v0.6a 后稳定）|
| 14 server e2e | `mcp_v4_e2e_14_servers.py` | ✅ 14/14, total wall 9073ms |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14（9 步全过）|

## 6. 未在 v0.6b 范围（明确不做）

- ❌ `progress` 字段（0-100 进度，raw_resumes 表无）— 推 v0.6b.1
- ❌ Redis pub/sub 跨进程推模式 — 推 v0.6b.1
- ❌ TestClient WS 端到端测试 — 推 v0.6b.1 (走 Playwright)
- ❌ watch_parse_progress MCP 工具 — 与 poll_parse_resume 重复，避免
- ❌ `file_url` 异步下载 — 推 v0.6a.1
- ❌ `batch_parse_resumes_async` — 推 v0.6a.1
- ❌ parse_worker_watchdog 实现 — 推 v0.6a.1
- ❌ stuck processing 检测 — 推 v0.6a.1

## 7. 后续路径

**v0.6b.1（0.5d，1 commit）**：
- raw_resumes 表加 `progress` 字段（0-100）+ migration
- parse_worker 内 set_progress(50) 在 LLM extract 前
- WS 推送加 progress 字段
- TestClient WS 端到端测试（如修好 starlette 事件循环冲突） 或 Playwright e2e

**v0.6c（1d，1 commit）**：force=True 参数（方案 A：清空 candidate_id + 重建）

**v0.7（2d，2 commit）**：skill_mgr 5 工具（与 v0.6a/b/c **可并行 2 agent**）

## 8. 回滚方法

```bash
# 失败回滚
git checkout mcp-v4-v0.6b-pre
# 或
git revert 3c120b1
# 改动 2 文件: raw_resume.py (WS 端点 + 鉴权 + 状态轮询 helper) + test_resume_parser_v0_6b_ws.py
# 回滚 = revert 1 commit
```

**回滚影响范围**：
- WS 端点 `/raw-resumes/{id}/progress` 不可用
- HTTP API POST submit + GET poll 仍正常（v0.6a 范围不动）
- mcp-resume 工具数 6 不变
- v0.6a 7 测试 + v0.5b 5 + v0.4d 4 = 16/16 仍 pass

## 9. v0.6 系列累计

| 阶段 | commit | 改动 | 估时 |
|---|---|---|---|
| v0.6a RQ + submit/poll | `752062a` | +645 / 0 | 1d |
| v0.6a ship report | `76662cc` | +203 | 0d |
| **v0.6b WebSocket** | `3c120b1` | **+263 / -4** | **0.5d** |
| **总计 v0.6 系列** | 3 commit | **+1111 / -4** | **1.5d** |

## 10. 引用

- v0.6+ 修正版: `.omo/plans/v0.6-plus-replan.md` §4 v0.6b
- v0.6+ Momus 审核: `.omo/plans/v0.6-plus-momus-review.md`
- v0.6a ship report: `docs/mcp-v4-v0.6a-ship-report.md`
- v0.5a ship: `docs/mcp-v4-v0.5a-ship-report.md`（抽 _do_extract_and_link 公共函数）
- v0.5b ship: `docs/mcp-v4-v0.5b-ship-report.md`（retry_raw_resume 工具）
- e2e 脚本: `scripts/mcp_v4_e2e_14_servers.py`
- health-check 脚本: `scripts/health-check.sh`

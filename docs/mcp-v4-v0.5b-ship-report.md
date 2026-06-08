# MCP v4 v0.5b Ship Report — retry_raw_resume 工具

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.5-replan.md` §4 v0.5b 任务拆解
> **Git tag**: `mcp-v4-v0.5b-pre` (commit 03d3e55, v0.5a ship report) → `mcp-v4-v0.5b-shipped` (commit efcd0a4)
> **commit**: 1 个 (`efcd0a4`) + 后续 ship report
> **依赖**: v0.5a `_do_extract_and_link` 公共函数（`commit 88066a3`）
> **接受门槛**: 5 新测试全 pass + mcp-resume list_tools 4 工具 + e2e 14/14 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| `_handle_retry_raw_resume` handler | ✅ |
| 状态校验（failed only）| ✅ |
| NOT_FOUND / CONFLICT 错误码 | ✅ |
| 调 `_do_extract_and_link` 复用 v0.5a 公共函数 | ✅ |
| mcp-resume list_tools 返回 4 工具 | ✅ parse_resume / batch_parse_resumes / get_candidate_profile / **retry_raw_resume** |
| 5 新测试 | ✅ 5/5 pass |
| v0.4d 4 测试（回归）| ✅ 4/4 pass |
| 总测试 | ✅ 9/9 pass |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14（9 步全过）|

## 2. 改动 diff

| 文件 | 改动 |
|---|---|
| `apps/api/app/tools/resume_parser.py` | +42 / 0（net +42）|
| `apps/api/app/tools/metadata.py` | +7 / 0 |
| `apps/api/tests/mcp/integration/test_resume_parser_v0_5b_retry.py` | +178（新建）|

总 +227 / 0（纯增量，零删除）。

## 3. 关键决策

### 3.1 状态机边界

`retry_raw_resume` 只接受 `status=failed` 的 raw_resume：

| 状态 | retry 行为 | 错误码 |
|---|---|---|
| `failed` | reset → processing → 调 `_do_extract_and_link` | — |
| `processing` | 拒收 | `CONFLICT`（"raw_resume 仍在处理中"）|
| `parsed` | 拒收 | `CONFLICT`（"raw_resume 已解析成功"）|
| 不存在 | 拒收 | `NOT_FOUND` |

**为什么不接 processing**：并发安全。同一 raw_resume 不允许两个 retry 并发触发（会出现 race condition 写 state）。`processing` 状态本质是"瞬态锁"。

**为什么不接 parsed**：已经成功解析的简历 retry 没意义（会重复创建候选人）。`force=True` 重链接语义按 v0.5-replan §5 推到 v0.6 单独 PR。

### 3.2 reset → processing 而非直接走 extract

retry handler 不直接调 LLM，先 reset 状态：

```python
rr.status = RawResumeStatus.PROCESSING
rr.error_message = None
raw_text = rr.raw_text
await db.commit()
```

**为什么不直接保留 failed 让 _do_extract_and_link 覆盖**：
- 状态机一致性：DB 里能观察到 retry 完整 transition `failed → processing → parsed/failed`
- 调试可观测：retry 期间外部 GET raw_resume 看到 `processing`（正在处理）
- _do_extract_and_link 不用改：复用现有 `processing → parsed/failed` 转换链

**commit 时机**：retry handler 第一个 commit 后，新 session 在 `_do_extract_and_link` 内 `db.get` 拿到的 `rr.status=processing`，走完整 transition。

### 3.3 调 _do_extract_and_link 而非重复实现

v0.5a 抽公共函数的最大价值在此体现：retry 工具**不**重写 LLM extract + 候选人创建 + 状态机落库逻辑，**直接调** `_do_extract_and_link(raw_resume_id, raw_text, auto_create=True)`。

**好处**：
- retry 与 parse_resume 走完全相同的成功/失败转换链（无分叉）
- v0.5a 抽函数时已被 v0.4d 4 测试覆盖（含 LLM 成功/失败路径），retry 自动获得这些保证
- 未来 v0.6 改 _do_extract_and_link 时 retry 自动同步（无重复维护）

**auto_create=True 强制**：retry 语义就是"重新建档/链候选人"，auto_create=False 没意义。

### 3.4 metadata.py retryable=False

`retry_raw_resume` 是**用户主动触发**的工具，不归 supervisor 自动 retry 范畴：

```python
register_tool(
    "retry_raw_resume",
    retryable=False,    # 手动触发，supervisor 不自动重试
    max_retries=0,
    escalation=EscalationMode.NONE,
)
```

**为什么**：supervisor 自动 retry 是为 transient error（如 LLM 5xx 抖一下）服务的；retry_raw_resume 是幂等性"按需重试"工具，调用方（用户/Agent）自己决定何时调。

## 4. 5 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_retry_failed_resume_succeeds_and_links_candidate` | 主路径：status=failed → processing → PARSED + candidate_id 链 |
| 2 | `test_retry_nonexistent_returns_NOT_FOUND` | raw_resume_id 不存在返 `NOT_FOUND` |
| 3 | `test_retry_processing_resume_returns_CONFLICT` | status=processing 拒收 |
| 4 | `test_retry_parsed_resume_returns_CONFLICT` | status=parsed 拒收 |
| 5 | `test_retry_llm_failure_keeps_status_failed` | retry 时 LLM 仍失败 → status 保持 FAILED + error_message 真值 |

**mock 模式**（沿用 v0.5a）：
- 直接 patch `app.tools.resume_parser.CandidateService`（无 3 层 MagicMock 嵌套）
- 1 个 `db.get` 通过 `call_count` side_effect 区分 retry 第一次拿 / extract 第二次拿
- 2 个 MagicMock 模拟同一 raw_resume 在 retry vs extract 两个 session 的状态

## 5. 退出门槛验证 / PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 5 新测试全 pass | `pytest tests/mcp/integration/test_resume_parser_v0_5b_retry.py` | ✅ 5/5 |
| mcp-resume list_tools 返回 4 工具 | 直接 spawn server + list_tools | ✅ parse_resume / batch_parse_resumes / get_candidate_profile / retry_raw_resume |
| e2e 14/14 仍 pass | `mcp_v4_e2e_14_servers.py` | ✅ 14/14 |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14 |

`mcp_v4_e2e_14_servers.py` 详情：
- mcp-resume tools=4（v0.4e 时 tools=3，v0.5b 加 1）
- 14 server 全部 P95/server ≤ 1024ms
- 总 wall time 9272ms（与 v0.5a 9250ms 持平）

`health-check.sh` 9 步详情：同 v0.5a，14/14 pass。

## 6. 未在 v0.5b 范围

按 `.omo/plans/v0.5-replan.md` §5 明确不做：

- ❌ `force=True` 参数（覆盖 candidate_id vs 创建新候选人，语义未定）
- ❌ (status, updated_at) 复合索引（retry 按 ID 查单条用不到）
- ❌ mcp-resume Bheavy 完整版（异步 LLM + WebSocket 进度推送，推 v0.6）
- ❌ Playwright 端到端测试（dev 栈未就绪，按 Phase D 推到 v1.1）
- ❌ 14 server 并行 spawn 压测（dev 机非 prod，推 v0.8）

## 7. 后续路径

**v0.6 候选**（按 v0.5-replan §6）：
- mcp-resume Bheavy 完整版（异步 LLM + WebSocket 进度推送）
- retry_raw_resume `force=True` 参数（语义：覆盖/创建新候选人）
- Phase C 剩余 (C.2 LLM retry / C.3 .env 整合 / C.5 datetime 修复 / C.6 docker healthcheck)

**v0.7+**：见 v0.5-replan.md §6。

## 8. 回滚方法

```bash
# 失败回滚
git checkout mcp-v4-v0.5b-pre   # 回到 v0.5b 改之前（v0.5a ship 状态）
# 或
git revert efcd0a4              # 撤销 v0.5b commit（v0.5a 仍保留）
```

**回滚影响范围**：
- `apps/api/app/tools/resume_parser.py`：删 42 行（`_handle_retry_raw_resume` + tools 列表项 + handlers 映射）
- `apps/api/app/tools/metadata.py`：删 7 行（register_tool）
- `apps/api/tests/mcp/integration/test_resume_parser_v0_5b_retry.py`：删整个文件（178 行）
- 总回滚 = revert 1 commit
- v0.5a `_do_extract_and_link` 公共函数**保留**（无影响，是 v0.5b 的依赖）

## 9. 引用 — v0.5 系列累计

| 阶段 | commit | 改动 | 估时 |
|---|---|---|---|
| v0.5a refactor | `88066a3` | 抽公共函数 + 恢复 LLM 成功测 +118/-51 | 0.5d |
| v0.5a ship report | `03d3e55` | docs +169 | 0d |
| v0.5b retry 工具 | `efcd0a4` | retry_raw_resume + 5 测试 +227 | 1d |
| **总计** | 3 commit | **+514 / -51** | **1.5d**（与 v0.5-replan.md §4 估时一致）|

## 10. 引用

- v0.5 重规划: `.omo/plans/v0.5-replan.md` §4
- v0.5a ship report: `docs/mcp-v4-v0.5a-ship-report.md`
- v0.4 ship report: `docs/mcp-v4-v0.4-ship-report.md`
- v0.4d ship (事务边界基线): `commit 1549b43`
- e2e 脚本: `scripts/mcp_v4_e2e_14_servers.py`
- health-check 脚本: `scripts/health-check.sh`

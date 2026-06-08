# MCP v4 v0.6c Ship Report — retry_raw_resume force=True 参数

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.6-plus-replan.md` §4 v0.6c
> **Git tag**: `mcp-v4-v0.6c-pre` (commit 957056d, v0.6b ship report) → `mcp-v4-v0.6c-shipped` (commit 2d7f85c)
> **commit**: 1 个 feat + 后续 ship report
> **接受门槛**: 4 新测试 + 23 回归 = 27/27 + e2e 14/14 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| `force` 参数 (默认 False) | ✅ |
| 工具定义加 force | ✅ |
| 状态机: force=True 清空 candidate_id | ✅ |
| 旧候选人留存 (方案 A 不 destructive) | ✅ 验证 svc.delete 不被调 |
| mcp-resume 工具数 | ✅ 仍 6 (force 是参数, 工具数不变) |
| 测试 | ✅ 4 新 + 23 回归 = 27/27 |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/tools/resume_parser.py` | +12 / -3 | force 参数 + 工具定义 |
| `apps/api/tests/mcp/integration/test_resume_parser_v0_6c_force.py` | +243 (新) | 4 测试 |
| **总** | **+255 / -3** | 2 文件 |

## 3. 关键决策

### 3.1 方案 A: 清空 candidate_id + 重建（Momus §3 决策点 3）

```python
async def _handle_retry_raw_resume(
    raw_resume_id: str = "",
    force: bool = False,
) -> dict[str, Any]:
    ...
    async with AsyncSessionLocal() as db:
        rr = await db.get(RawResume, raw_resume_id)
        ...
        old_candidate_id = rr.candidate_id
        if force:
            rr.candidate_id = None  # v0.6c 方案 A: 清空
            logger.info("retry force=True: cleared candidate_id=%s", old_candidate_id)
        rr.status = RawResumeStatus.PROCESSING
        rr.error_message = None
        raw_text = rr.raw_text
        await db.commit()
    
    return await _do_extract_and_link(raw_resume_id, raw_text, auto_create=True)
```

**为什么方案 A 而非 B/C/D**：
- 方案 B（覆盖原 candidate）: 需要 svc.update() 路径，破坏 v0.5a 抽函数零差异原则
- 方案 C（不创建不更新）: 用户视角没价值
- 方案 D（保持原 candidate_id，重跑 LLM extract）: 等价于不 retry
- **方案 A**（清空 + 重建）: 与 v0.5b retry 默认行为结构一致，零额外依赖

### 3.2 旧候选人不自动删（方案 A 不 destructive）

**明确不调** `CandidateService.delete(candidate_id)`。理由：
- 删除是 destructive 操作，应该用户主动 archive（UI 按钮触发）
- v0.6c force=True 是"重跑解析"，不是"删旧建新"
- 旧候选人保留供 user 决策（archive / 合并 / 丢弃）

测试 4 显式验证 `svc.delete` 不被调（用 `deleted_ids` 列表记录）：
```python
assert deleted_ids == [], f"force=True 不应自动删旧候选人"
```

### 3.3 ⚠️ force 语义限制（必须显式声明）

**v0.5b retry 默认行为已经会创建新候选人**（`_do_extract_and_link` 总是新建 + 覆盖 `rr.candidate_id`）。所以：

| 路径 | retry handler 写入 | _do_extract_and_link 写入 | 最终 `rr.candidate_id` |
|---|---|---|---|
| force=False (v0.5b) | 保持旧值 | 覆盖成新值 | **新值** |
| force=True (v0.6c) | 清空成 None | 覆盖成新值 | **新值** |

**两种路径的最终结果等价**——`rr.candidate_id` 都是新值（旧值都丢失）。

**唯一差异**：retry handler 提交后，**下一次 `db.get` 看到的中间态**：
- force=False 路径：`rr.candidate_id = 旧值`
- force=True 路径：`rr.candidate_id = None`

**对用户/前端的影响**：
- 如果 UI 实时监听 `raw_resumes.candidate_id` 变化 → force=True 出现短暂 None
- 如果只调最终结果（GET /status）→ 无差异

**真正差异化语义**（如 force=False 时复用旧 candidate_id 做 update 而非 create）需要修改 `_do_extract_and_link` 增加 `reuse_candidate_id` 参数 + svc.update() 路径。**推 v0.6c.1 单独 PR 定义**。

## 4. 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_retry_default_no_force_arg_works` | 默认 force=False 走 v0.5b 主路径, 最终 candidate_id 覆盖成新值 |
| 2 | `test_retry_force_false_keeps_old_candidate_id_in_path` | force=False 路径上, retry handler 提交后, 下次 db.get 看到 candidate_id = 旧值 |
| 3 | `test_retry_force_true_clears_candidate_id_in_path` | force=True 路径上, retry handler 提交后, 下次 db.get 看到 candidate_id = None (被清空) |
| 4 | `test_retry_force_true_creates_new_candidate_with_different_id` | force=True 完整路径: 新候选人创建, 旧候选人**不**被 svc.delete, 最终 candidate_id = 新值 |

**mock 模式**（沿用 v0.5b 5 测试）：
- 2 个 MagicMock 模拟 retry 第一次 + extract 第二次的 raw_resume 状态
- 1 个 db.get 通过 call_count side_effect 区分两次调用
- 显式 mock svc.delete（即使它**不**被调，记录调用列表验证不 destructive）

## 5. 退出门槛验证 / PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 4 新测试 + 23 回归 = 27/27 | `pytest tests/mcp/integration/test_resume_parser_v0_6{c,b,a,5b,4d}*.py` | ✅ 27 passed |
| mcp-resume list_tools 6 工具 | e2e 14/14 跑 | ✅ 6 工具（force 是参数, 工具数不变）|
| 14 server e2e | `mcp_v4_e2e_14_servers.py` | ✅ 14/14, total wall 9117ms |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14（9 步全过）|

## 6. 未在 v0.6c 范围（明确不做）

- ❌ force=True 真正差异化语义（复用旧 candidate_id 做 update 而非 create）— 推 v0.6c.1
- ❌ 旧候选人自动 archive（destructive 操作，需用户主动）— 推后续
- ❌ 旧候选人合并到新候选人（如 phone/email dedup）— 不在 v0.6c 范围
- ❌ raw_resumes 增量更新（如 last_retried_at 字段）— 不在 v0.6c 范围

## 7. 后续路径

**v0.6c.1（0.5d，1 commit）— 真正差异化 force 语义**：
- 修改 `_do_extract_and_link` 加 `reuse_candidate_id: bool = False` 参数
- force=False 调 `_do_extract_and_link(reuse_candidate_id=True)` → svc.update() 而非 svc.create()
- force=True 调 `_do_extract_and_link(reuse_candidate_id=False)` → svc.create() 新建
- 真正语义: force=False **复用**旧候选人, force=True **创建**新候选人

**v0.7（2d，2 commit）**：skill_mgr 5 工具

**v0.8 / v1.0**：见 v0.6-plus-replan §5

## 8. 回滚方法

```bash
# 失败回滚
git checkout mcp-v4-v0.6c-pre
# 或
git revert 2d7f85c
# 改动 2 文件: resume_parser.py (force 参数) + test_resume_parser_v0_6c_force.py
# 回滚 = revert 1 commit
```

**回滚影响范围**：
- retry_raw_resume 工具定义恢复 v0.5b（无 force 参数）
- v0.5b 5 测试仍 pass
- v0.6a 7 测试 + v0.6b 7 测试 + v0.4d 4 测试 = 18/18 仍 pass

## 9. v0.6 系列累计

| 阶段 | commit | 改动 | 估时 |
|---|---|---|---|
| v0.6a RQ + submit/poll | `752062a` | +645 / 0 | 1d |
| v0.6a ship report | `76662cc` | +203 | 0d |
| v0.6b WebSocket | `3c120b1` | +263 / -4 | 0.5d |
| v0.6b ship report | `957056d` | +218 | 0d |
| **v0.6c force=True** | `2d7f85c` | **+255 / -3** | **0.5d** |
| **总计 v0.6 系列** | 5 commit | **+1584 / -7** | **2d** |

## 10. 引用

- v0.6+ 修正版: `.omo/plans/v0.6-plus-replan.md` §4 v0.6c
- v0.6+ Momus 审核: `.omo/plans/v0.6-plus-momus-review.md` §1.1（force 语义重新定义）
- v0.6a ship: `docs/mcp-v4-v0.6a-ship-report.md`（RQ worker + submit/poll）
- v0.6b ship: `docs/mcp-v4-v0.6b-ship-report.md`（WebSocket 进度推送）
- v0.5b ship: `docs/mcp-v4-v0.5b-ship-report.md`（retry_raw_resume 工具）
- e2e 脚本: `scripts/mcp_v4_e2e_14_servers.py`
- health-check 脚本: `scripts/health-check.sh`

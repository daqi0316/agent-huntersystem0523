# MCP v4 v0.6c.1 Ship Report — retry_raw_resume force=True 真差异化语义

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.6c-momus-review.md` (Momus 审核修正版 v0.6c.1 计划)
> **Git tag**: `mcp-v4-v0.6c.1-pre` (commit 0c2f478, Momus 审核 plan) → `mcp-v4-v0.6c.1-shipped` (commit e69c190)
> **commit**: 1 个 feat + 后续 ship report
> **接受门槛**: 6 新测试 + 改 1 测试 + 26 回归 = 33/33 + e2e 14/14 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| `_do_extract_and_link` 加 `reuse_candidate_id` 参数 | ✅ |
| `reuse_candidate_id=True` 路径: svc.update() 复用旧候选人 | ✅ |
| `reuse_candidate_id=True` 路径: svc.update 返 None 时 fallback create | ✅ |
| `reuse_candidate_id=False` 路径: svc.create() 创建新 (v0.5a 行为) | ✅ |
| `_handle_retry_raw_resume` force 路径分发 | ✅ |
| force=False → reuse=True (svc.update 旧) | ✅ |
| force=True → reuse=False (svc.create 新) | ✅ |
| 旧候选人不自动删 (方案 A) | ✅ |
| v0.6c 测试 1 改 (兼容 v0.6c.1 新语义) | ✅ |
| v0.6c.1 6 新测试 | ✅ 6/6 |
| 测试累计 | ✅ 33/33 |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/tools/resume_parser.py` | +75 / -27 | _do_extract_and_link 加 reuse_candidate_id + _handle_retry_raw_resume 路径分发 + 工具 description 更新 |
| `apps/api/tests/mcp/integration/test_resume_parser_v0_6c_force.py` | +20 / -15 | 改测试 1 适配 v0.6c.1 新语义 |
| `apps/api/tests/mcp/integration/test_resume_parser_v0_6c1_force_diff.py` | +367 (新) | 6 新测试 |
| **总** | **+462 / -42** | 3 文件 |

## 3. 关键决策

### 3.1 真差异化 force 语义（Momus §2.1）

```python
# v0.6c.1: _do_extract_and_link 加 reuse_candidate_id
if reuse_candidate_id and existing_candidate_id:
    # 路径 A: svc.update() 复用旧候选人
    updated = await svc.update(existing_candidate_id, update_data)
    if updated is None:
        # candidate 已被外部删, fallback create
        created = await svc.create(create_data)
        candidate_id = created.id
    else:
        candidate_id = updated.id
        reused = True
else:
    # 路径 B: svc.create() 创建新 (v0.5a 行为)
    created = await svc.create(create_data)
    candidate_id = created.id
```

| 路径 | force | svc 调用 | raw_resumes.candidate_id |
|---|---|---|---|
| **force=False (默认)** | reuse=True | `svc.update(existing_id, new_data)` | **保持** 原 ID |
| **force=True** | reuse=False | `svc.create(new_data)` | **覆盖** 成新 ID (旧 ID 丢失) |
| force=False 但 candidate 不存在 | reuse=True | fallback `svc.create` | 覆盖成新 ID |
| force=False 但 svc.update 抛异常 | 非阻塞 | except 捕获, log warning | status=PARSED (v0.5a 非阻塞) |

### 3.2 reuse 路径保持 candidate_id（不覆盖）

```python
# v0.6c.1: 末尾写 rr.candidate_id: reuse 路径保持, 非 reuse 路径覆盖
if not reused:
    rr.candidate_id = candidate_id or None
# else: 保持原 candidate_id (reused=True 时)
```

**为什么 `reused` 标志**：
- reuse 路径：candidate_id 已存在（来自 existing_candidate_id），不需要再写
- 非 reuse 路径：candidate_id 是新建的，需要写 rr.candidate_id 覆盖

### 3.3 fallback create（svc.update 返 None）

```python
if updated is None:
    # candidate 已被外部删, fallback create
    create_data = CandidateCreate(...)
    created = await svc.create(create_data)
    candidate_id = created.id
    logger.info("fallback create candidate %s (old %s deleted)", candidate_id, existing_candidate_id)
```

**为什么需要 fallback**：
- `svc.update` 内部 `get_by_id` 返 None 时**不抛异常**而返 None（v0.5a 行为）
- 如果直接 `await svc.update()` 后用返回值 → 已覆盖原 candidate_id 为 "" → rr.candidate_id = None（**但 retry 成功状态错**）
- fallback create 避免这种 silent failure

### 3.4 非阻塞错误处理（v0.5a 设计延续）

svc.create / svc.update 抛异常时，`_do_extract_and_link` 走 `except Exception` 捕获 + `logger.warning`，**不**写 status=FAILED。

**测试 4 + 5 验**：
- `test_force_false_update_failure_is_non_blocking_status_parsed` — status=PARSED (LLM 已成功)
- `test_force_true_create_failure_is_non_blocking_status_parsed` — status=PARSED

**这是 v0.5a 设计**：candidate 创建/更新失败**不**影响 LLM 解析状态（已 PARSED），只 log warning。retry 路径同样适用。

### 3.5 v0.6c 测试 1 改（破坏性变更兼容性）

v0.6c 测试 1 `test_retry_default_no_force_arg_works`：
- **v0.6c 原意**：force=False 走 create 路径（v0.5b 默认行为）
- **v0.6c.1 改后**：force=False 走 update 路径

**测试改**：
- 改 mock `svc.create` → mock `svc.update` 返 fake_updated
- 验 svc.update 被调（不是 svc.create）
- 验 `rr.candidate_id` 保持旧值（不被覆盖）
- 验 `create_called = False`（fallback 路径也未触发）

## 4. 测试设计

### 4.1 v0.6c 4 测试（1 改 + 3 保留）

| # | 测试 | 改/保留 | 覆盖 |
|---|---|---|---|
| 1 | `test_retry_default_no_force_arg_works` | **改** | force=False 走 update 路径, 验 update 被调 + candidate_id 保持 |
| 2 | `test_retry_force_false_keeps_old_candidate_id_in_path` | 保留 | force=False 路径中间态 candidate_id 仍 = 旧值 |
| 3 | `test_retry_force_true_clears_candidate_id_in_path` | 保留 | force=True 清空后 → status=FAILED (LLM 失败) |
| 4 | `test_retry_force_true_creates_new_candidate_with_different_id` | 保留 | force=True 调 create 新候选人, 旧留存 |

### 4.2 v0.6c.1 6 新测试

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_force_false_calls_svc_update_with_existing_candidate_id_and_new_data` | 主路径：force=False 调 svc.update, candidate_id 参数 = 原值, update_data 含新解析字段 |
| 2 | `test_force_false_falls_back_to_create_when_svc_update_returns_none` | candidate 已被外部删 (svc.update 返 None) 时 fallback svc.create |
| 3 | `test_force_true_creates_new_candidate_and_does_not_call_update` | force=True 调 svc.create, 验 svc.update 不被调 |
| 4 | `test_force_false_update_failure_is_non_blocking_status_parsed` | svc.update 抛异常时 status=PARSED (v0.5a 非阻塞) |
| 5 | `test_force_true_create_failure_is_non_blocking_status_parsed` | svc.create 抛异常时 status=PARSED |
| 6 | `test_force_true_old_candidate_not_deleted` | 旧候选人留存 (svc.delete 不被调) |

## 5. ⚠️ 破坏性变更（Momus §2.4 显式预警）

**v0.6c.1 后 retry_raw_resume 默认行为**：

| 调用 | v0.6c (前) | v0.6c.1 (后) |
|---|---|---|
| `retry_raw_resume(rr_id)` 默认 (无 force) | 创建新候选人 + 旧留存 (垃圾) | **更新原候选人** (raw_resumes.candidate_id 保持) |
| `retry_raw_resume(rr_id, force=True)` | 创建新候选人 + 旧留存 (垃圾) | 创建新候选人 + 旧留存 (垃圾) |
| `retry_raw_resume(rr_id, force=False)` 显式 | 创建新候选人 + 旧留存 (垃圾) | 更新原候选人 |

**影响范围**：
- 前端 UI：retry 按钮默认行为变化（从"创建新"变"更新原"）
- Agent / 自动化：retry 调用默认行为变化
- 旧候选人 GC 策略：v0.6c.1 之前留下的"新候选人 + 旧留存垃圾"需手动 cleanup

**降低风险建议**：
- v0.6c.1 ship 时通知前端
- 提供 `force=True` 显式选择保留 v0.6c 行为（创建新）
- 文档明确 force 语义变更（changelog / API doc）

## 6. 退出门槛验证 / PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 6 新测试 + 改 1 + 26 回归 = 33/33 | `pytest tests/mcp/integration/test_resume_parser_v0_6{c.1, c, b, a, 5b, 4d}*.py` | ✅ 33 passed |
| mcp-resume list_tools 6 工具 | e2e 14/14 跑 | ✅ 6 工具（force 是参数, 工具数不变）|
| 14 server e2e | `mcp_v4_e2e_14_servers.py` | ✅ 14/14, total wall 9142ms |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14（9 步全过）|

## 7. 未在 v0.6c.1 范围（明确不做）

- ❌ 旧候选人自动 archive / cleanup — 推后续
- ❌ 旧候选人合并到新候选人 (phone/email dedup) — 不在 v0.6c.1 范围
- ❌ raw_resumes 增量字段 (last_retried_at) — 不在 v0.6c.1 范围
- ❌ 旧候选人 / 新候选人 关系表 — 不在 v0.6c.1 范围
- ❌ force=False 路径上 svc.update 失败的 retry 链 (写 status=FAILED 重试) — v0.5a 设计是非阻塞, 推后续

## 8. 后续路径

**v0.7（2d，2 commit）**：skill_mgr 5 工具
**v0.8（1d，1 commit）**：14 server 并行 spawn 压测
**v1.0a + v1.0b**：.env 整合 + datetime 修复

## 9. 回滚方法

```bash
# 失败回滚
git checkout mcp-v4-v0.6c.1-pre
# 或
git revert e69c190
# 改动 3 文件: resume_parser.py + test_resume_parser_v0_6c_force.py + test_resume_parser_v0_6c1_force_diff.py
# 回滚 = revert 1 commit
```

**回滚影响范围**：
- `_do_extract_and_link` 恢复 v0.6c（无 reuse_candidate_id 参数）
- `_handle_retry_raw_resume` 恢复 v0.6c（force 参数保留, 但只清空 candidate_id 不实际差异化）
- v0.6c 4 测试恢复（force=False 走 create 假设）
- v0.6c.1 6 测试删
- **v0.5a + v0.5b + v0.6a + v0.6b 26 测试仍 pass** (无共享代码改动)

## 10. v0.6 系列累计

| 阶段 | commit | 改动 | 估时 |
|---|---|---|---|
| v0.6a RQ + submit/poll | `752062a` | +645 | 1d |
| v0.6a ship report | `76662cc` | +203 | 0d |
| v0.6b WebSocket | `3c120b1` | +263 | 0.5d |
| v0.6b ship report | `957056d` | +218 | 0d |
| v0.6c force=True (无效) | `2d7f85c` | +255 | 0.5d |
| v0.6c ship report | `9cae888` | +171 | 0d |
| **v0.6c.1 真差异化** | `e69c190` | **+462 / -42** | **0.5d** |
| **总计 v0.6 系列** | 7 commit | **+2217 / -49** | **2.5d** |

## 11. 引用

- v0.6c.1 计划: `.omo/plans/v0.6c-momus-review.md` §2 Momus 修正版
- v0.6c Momus 审核: `.omo/plans/v0.6c-momus-review.md` §1 (6 项 gap)
- v0.6c ship: `docs/mcp-v4-v0.6c-ship-report.md` (承认 force 语义限制)
- v0.6+ 修正版: `.omo/plans/v0.6-plus-replan.md` §4 v0.6c (设计意图)
- v0.6+ Momus 审核: `.omo/plans/v0.6-plus-momus-review.md` §1.1
- v0.5a 抽函数: `commit 88066a3` + `docs/mcp-v4-v0.5a-ship-report.md`
- v0.5b retry: `commit efcd0a4` + `docs/mcp-v4-v0.5b-ship-report.md`
- svc.update: `apps/api/app/services/candidate.py:77`
- CandidateUpdate schema: `apps/api/app/schemas/candidate.py:18`

## 7. 后续

- (F2 retrofit 标 — 22 老 mcp-v4-v* ship report 同步升级到 G8 模板)
- followups.md 总索引 (F1-F22 + G11-G18) 持续维护
- Phase D 远期 (按 docs/phase-d-session-plan.md 11 session 计划)

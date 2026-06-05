# Plan: Schema 漂移修复 + Emergency Stop Bug 修复 + 防再发（Momus 审核版）

> 上次审核被 Momus 驳回（漂移范围未核实、修复方向不明确、pre-commit 设计粗糙、依赖关系缺失）。
> 本版 plan 已逐项修正。

## 0. Context

**生产事故**：Dashboard 500 (`InvalidTextRepresentationError` on approval_status enum)。
**上次修复**：把 `SAEnum(EnumClass, name=...)` 改用 `enum_column()` 工厂（强制 `values_callable`），3 个 model 改动 + 7 个集成测试。

**本次新发现**（上次 plan Out of Scope 漏掉的真阻塞 bug）：
1. **`resolve()` 在生产路径上 500** — `approvals.id` / `recommendations.*` 等列在 DB 实际是 `varchar`，但 model 声明 `UUID(as_uuid=False)`，导致 SQLAlchemy 生成 `WHERE id = $1::UUID` 跟 DB `varchar` 列不匹配 → `UndefinedFunctionError`。**用户点 approve/reject 即触发**。
2. **`_pending_purge_all` 是真 bug** — SQLAlchemy 编译输出 `UPDATE approvals SET <所有列>=:param WHERE status='pending'`，实际把 PENDING 的 proposal/params/action_type 等清空。**emergency stop 安全功能错行为**。
3. **缺防再发** — `.pre-commit-config.yaml` 已有 ruff，但缺 model 模式校验。

## 1. 精确影响面（已用 SQL 核实，2026-06-03 15:30）

### 1.1 Schema 漂移（model `UUID(as_uuid=False)` vs DB `varchar`）

| model 文件 | 列 | DB | model | 阻塞生产？ |
|---|---|---|---|---|
| `approval.py` | `id`, `user_id`, `resolver_id` (3) | varchar | UUID(as_uuid=False) | ✅ **`resolve()` 500** |
| `recommendation.py` | `id`, `user_id`, `candidate_id`, `job_id` (4) | varchar | UUID(as_uuid=False) | ✅ 推荐读写 500 |
| `operation_log.py` | `user_id` (1) | varchar | UUID(as_uuid=False) | 独立（不影响主路径） |
| `command_audit_log.py` | `id`, `user_id` (2) | varchar | UUID(as_uuid=False) | 独立 |
| `interview_evaluation.py` | `id`, `interview_id` (2) | uuid（表未建，但保持 model 同步） | UUID(as_uuid=False) | 预防 |
| **合计** | **12 列 / 5 文件** | | | |

### 1.2 **不**漂移的（已用 SQL 核实，不要动）

- `user.py` — id 用 `String(36)` ✅
- `conversation.py` — id/user_id 用 `String(36)` ✅
- `mcp_server.py` / `memory_fact.py` / `setting.py` / `session_summary.py` — 全部 `String(36)` ✅
- `application.py` / `candidate.py` / `interview.py` / `job_position.py` — model `UUID(as_uuid=False)`，DB 实际 `uuid`，**匹配** ✅
- `interview_evaluation.py` — DB 表未建，但 model 用 `UUID(as_uuid=False)`，**未来建表会撞坑** — 顺手改

### 1.3 `_pending_purge_all` 实际行为（已用 `compile(literal_binds)` 验证）

```sql
UPDATE approvals SET id=:id, user_id=:user_id, action_type=:action_type, ..., 
                     updated_at=:updated_at WHERE approvals.status = 'pending'
```

**SQLAlchemy 默认行为**：`update(Approval).where(...)` 不设 values 时，会生成"UPDATE 全表所有列"语句，参数值都是 None/default。
**实际效果**：proposal/params/action_type 等被清空，**等于软删除**而非"标记为 CANCELLED"。
**修复**：加 `.values(status=ApprovalStatus.CANCELLED, resolved_at=now)`。

## 2. 修复策略

### 2.1 修复方向：改 model 同步 DB（**唯一推荐**）

**理由**（按优先级）：
1. **回滚成本 = 0**：只改 Python model 文件，DB schema 不动，重启即可回滚
2. **数据零迁移**：DB 已是 varchar，所有现存数据天然兼容
3. **无停机风险**：model 列类型从 `UUID(as_uuid=False)` 改成 `String(36)`，对外契约不变（仍接受 36 字符 UUID 字符串）
4. **方向 B（改 DB 同步 model）**需要 `ALTER TABLE ... TYPE UUID USING id::UUID`：
   - 需要数据迁移 + 锁表
   - 回滚成本极高
   - **风险 > 收益**，否决

**统一工厂**：在 `app/models/_base.py` 加 `uuid_str_column()` 工厂，与 `enum_column` 并列，**禁止** 直接 `mapped_column(UUID(as_uuid=False), ...)`。

### 2.2 修复方式：直接 `String(36)` 替换（**无工厂**）

**为何不引入 UUID 工厂**（与 enum 工厂不同）：

| 维度 | enum 工厂 | UUID 工厂（**否决**） |
|---|---|---|
| 防误用价值 | 高（`values_callable` 是 SQLAlchemy 私有参数） | 低（`String(36)` 本身就是显式标准调用） |
| 抽象复杂度 | 中（enum 类型/值/序列化隐藏） | 低（一行 type 替换，无隐藏行为） |
| 静态扫描覆盖 | 难（模式复杂：SAEnum(Cls, name=..., values_callable=...) 正确写法也会被误报） | 简单（一行 grep 即可） |
| 维护成本 | 中（每次新 enum 类型要保持一致） | 低（替换后 5 年不动） |

**结论**：
- `enum_column` 工厂**保留并扩展**（已有价值）
- UUID 列**直接 `String(36)` 替换**，不引入新工厂
- 防再发靠 G 阶段静态扫描（`scripts/check_model_patterns.py`），一行 `grep UUID(as_uuid=False) apps/api/app/models/`

**实际改动**：

```python
# 改之前
from sqlalchemy.dialects.postgresql import UUID
id: Mapped[str] = mapped_column(
    UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()),
)

# 改之后
id: Mapped[str] = mapped_column(
    String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
)
```

### 2.3 依赖图

```
[阶段 D.2-D.4: 替换 4 个 model 文件中的 UUID(as_uuid=False) → String(36)]
   ↓
[阶段 D.5: 跑 mock 测试不回归]
   ↓
[阶段 E: 修 _pending_purge_all]
   ↓
[阶段 F.1: 扩展集成测试]
   ↓
[阶段 F.2: 跑集成测试]
   ↓
[阶段 G.1: 写防再发脚本（扫 UUID(as_uuid=False) + SAEnum 裸调用）]
   ↓
[阶段 G.2: 配 pre-commit]
   ↓
[阶段 H.1-H.2: 全套测试 + 手动验证]
```

不能反序：先加 pre-commit 会扫到未修的代码（噪音）；先做测试无法验证修复。

## 3. 阶段化执行（每步 1-3 个工具调用）

### 阶段 D：Schema 漂移修复（生产阻塞）

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| D.1 | `app/models/_base.py` | **不新增 UUID 工厂**（详见 §2.2 决策表） | 已有 enum_column 工厂不变 |
| D.2 | `app/models/approval.py` | 4 个 `UUID(as_uuid=False)` → `String(36)` | `pytest tests/test_approval_service.py` 不回归 |
| D.3 | `app/models/recommendation.py` | 4 个 `UUID(as_uuid=False)` → `String(36)` | 不回归 |
| D.4 | `app/models/operation_log.py` (1 列) + `app/models/command_audit_log.py` (2 列) + `app/models/interview_evaluation.py` (2 列) | 共 5 列 | 不回归 |
| D.5 | 跑现有所有 mock 测试 | `pytest tests/ --ignore=tests/test_models_enum_integration.py -q` | 0 回归 |

### 阶段 E：Emergency Stop Bug 修复

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| E | `app/agents/human_loop.py` | `_pending_purge_all` 加 `.values(status=ApprovalStatus.CANCELLED, resolved_at=now)` | 编译 SQL 不再 SET 全表 |

### 阶段 F：集成测试

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| F.1a | `tests/test_models_enum_integration.py` 扩展 | `TestApprovalStatusRoundTrip::test_resolve_works_with_varchar_id` — 走 `svc.resolve()` 整链路 | 修复前 500，修复后 pass |
| F.1b | 同上 | `TestEmergencyStop::test_purge_marks_cancelled_not_clears_data` — 验证 purge 不清空 proposal/params | 修复前 fail（action_type 被清空），修复后 pass |
| F.1c | 同上 | `TestSchemaDriftRegression::test_no_bare_uuid_as_uuid_false` — 静态扫描禁止 `mapped_column(UUID(as_uuid=False), ...)` | 静态防护 |
| F.2 | 跑 `tests/test_models_enum_integration.py` | 全部通过 | ✅ |

### 阶段 G：Pre-commit 防再发

| 步骤 | 文件 | 改动 | 验证 |
|---|---|---|---|
| G.1 | `scripts/check_model_patterns.py` | Python 脚本：扫所有 `app/models/*.py`，禁止 `UUID(as_uuid=False)` 裸调用，禁止 `SAEnum(EnumClass, name=...)` 裸调用 | `python scripts/check_model_patterns.py` exit 0 |
| G.2 | `.pre-commit-config.yaml` | 加 local hook 调用 G.1 | `pre-commit run --all-files` 干净 |

### 阶段 H：回归 + 手动验证

| 步骤 | 验证项 | 通过标准 |
|---|---|---|
| H.1 | `pytest tests/ -k "not integration"` | 86+ mock 测试 0 失败 |
| H.1' | `pytest tests/test_models_enum_integration.py` | 9+ 集成测试全绿 |
| H.2 | 手动模拟生产路径 | `create → resolve → expire → list_pending` 全部 200，无 `UndefinedFunctionError` |

## 4. 成功标准（Done Definition）

| 验证项 | 通过标准 |
|---|---|
| `svc.resolve(approval_id, ...)` | 调 `svc.resolve()` 不抛 `UndefinedFunctionError`；raw SQL 读 `status::text == 'approved'`；`proposal`/`params`/`action_type` 内容完整 |
| `recommendation` ORM 操作 | `INSERT`/`UPDATE` 不 500 |
| `_pending_purge_all()` | 跑后 `proposal`/`params`/`action_type` **未被清空**，仅 `status='cancelled'` |
| `scripts/check_model_patterns.py` | exit 0 |
| `pre-commit run --all-files` | 干净 |
| `pytest tests/ --ignore=tests/test_models_enum_integration.py` | 86+ mock 测试 0 失败 |
| `pytest tests/test_models_enum_integration.py` | 9+ 集成测试全绿 |
| 手动 `create → resolve → expire → list_pending` | 全部不抛异常 |

## 5. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 改 `String(36)` 后 SQLAlchemy 类型推断错 | 极低 | 中 | 集成测试覆盖 `resolve()` 整链路 |
| FK 列改错导致 FK 约束失效 | 低 | 高 | **保留 `ForeignKey("users.id", ondelete="CASCADE")` 调用结构不变，仅替换列类型参数**；集成测试覆盖 resolve |
| 漂移修复漏改某列 | 中 | 中 | G 阶段静态扫描 `UUID(as_uuid=False)` 防漏 |
| pre-commit hook 误报正确代码 | 低 | 低 | 工厂调用白名单豁免 |
| 死代码 `from sqlalchemy.dialects.postgresql import UUID` | 中 | 低 | D.2-D.4 改列同时清理 import |

## 6. 回滚

```bash
git revert <commit>
# DB 不动
# 重启后原 500 bug 复现 — 确认是 model 列类型问题
```

## 7. Out of Scope（明确不做）

- ❌ 前端 `ApprovalCountdown` 容错（独立 task）
- ❌ pre-commit 加 ruff-format 修改（已存在，**不重复配置**）
- ❌ 把 `interview_evaluations` 表的 DB 类型从无改成某类型（表未建，建表由 alembic 决定）
- ❌ 把 `conversation.py` / `mcp_servers.py` 等已用 String(36) 的 model 改格式（已经对）
- ❌ 大规模统一所有表都用 native UUID（方向 B，否决）

## 8. 文件清单（精确改动列表）

**新建**（2）：
- `apps/api/scripts/check_model_patterns.py`
- `.omo/plans/schema-drift-and-purge-fix.md`（本文件）

**修改**（7）：
- `apps/api/app/models/approval.py`（4 列：id, user_id, target_id, resolver_id）
- `apps/api/app/models/recommendation.py`（4 列：id, user_id, candidate_id, job_id）
- `apps/api/app/models/operation_log.py`（1 列：user_id）
- `apps/api/app/models/command_audit_log.py`（2 列：id, user_id）
- `apps/api/app/models/interview_evaluation.py`（2 列：id, interview_id，预防）
- `apps/api/app/agents/human_loop.py`（1 行 `_pending_purge_all` 修复）
- `apps/api/tests/test_models_enum_integration.py`（3 个新测试）
- `.pre-commit-config.yaml`（加 1 个 local hook）

**总计**：~13 列类型修复 + 1 行 emergency stop 修复 + 3 个新测试 + 1 个 pre-commit hook。

## 9. 时间预估

| 阶段 | 步骤数 | 时间 |
|---|---|---|
| D（schema 修复） | 4 | 8 分钟 |
| E（purge 修复） | 1 | 2 分钟 |
| F（测试） | 2 | 10 分钟 |
| G（pre-commit） | 2 | 5 分钟 |
| H（验证） | 2 | 3 分钟 |
| **总计** | **11** | **~28 分钟** |

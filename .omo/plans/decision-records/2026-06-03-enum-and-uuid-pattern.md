# ADR-2026-06-03: SQLAlchemy Enum & UUID 列模式

- **Status**: Accepted
- **Date**: 2026-06-03
- **Deciders**: Backend team
- **Related**: `.omo/plans/approval-enum-fix.md`, `.omo/plans/schema-drift-and-purge-fix.md`

## Context

2026-06-03 Dashboard 500，根因两次出现：

1. **`SAEnum(EnumClass, name=...)` 写库用 enum `name`（大写）**，但 PostgreSQL `approval_status` enum label 实际是 `value`（小写 `pending/expired/...`），触发 `InvalidTextRepresentationError`。
2. **`UUID(as_uuid=False)` model 列**，但 PostgreSQL 实际是 `varchar`，ORM `WHERE id = $1::UUID` 跟 `varchar` 列不匹配，触发 `UndefinedFunctionError`。`svc.resolve()` 整条生产路径（用户点 approve/reject）都会触发。

两次都是**model 声明与 DB 实际不一致**——但本地 mock 测试用 `AsyncMock` 完全屏蔽 DB，未能发现。

## Decision

### 1. Enum 列：必须用 `enum_column()` 工厂（小写 value 场景）

```python
# apps/api/app/models/_base.py 提供
def enum_column(py_enum: type[E], name: str) -> SAEnum:
    return SAEnum(
        py_enum,
        name=name,
        values_callable=lambda members: [e.value for e in members],
    )
```

**强制写库用 `value`**。适用于 DB label 是 enum `value`（小写）的场景：

| Enum | DB label | Model | 写法 |
|---|---|---|---|
| `ApprovalStatus` | `pending/...` | `PENDING = "pending"` | ✅ `enum_column()` |
| `RecommendationType` | `candidate_job_match/...` | `CANDIDATE_JOB_MATCH = "..."` | ✅ `enum_column()` |
| `CandidateStatus` | `active/...` | `ACTIVE = "active"` | ✅ `enum_column()` |
| `InterviewRound` | (表未建) | `R1 = "phone_screen"` | ✅ `enum_column()` |
| `EvaluationVerdict` | (表未建) | `STRONG_HIRE = "strong_hire"` | ✅ `enum_column()` |

### 2. Enum 列：保留 `SAEnum` 裸调用（大写 name == DB label 场景）

**当 DB label 与 enum `name` 都是大写时**（如 `PENDING`/`PENDING`），`SAEnum` 默认写库用 `name`，**碰巧正确**。**不要改成 `enum_column()`**——改成 `enum_column()` 会写小写 `value`，与 DB label 不匹配，立即 500。

不要把 `value` 改成大写去"统一"——会破坏所有 `.value` 调用方（`schedule_tool.py` / `application.py` / `permissions.py` 等）。

适用枚举（保留 `SAEnum`）：

| Enum | DB label | Model | 写法 |
|---|---|---|---|
| `ApplicationStatus` | `PENDING/...` | `PENDING = "pending"` | 保留 `SAEnum` |
| `InterviewType` | `PHONE/...` | `PHONE = "phone"` | 保留 `SAEnum` |
| `InterviewStatus` | `SCHEDULED/...` | `SCHEDULED = "scheduled"` | 保留 `SAEnum` |
| `JobStatus` | `DRAFT/...` | `DRAFT = "draft"` | 保留 `SAEnum` |
| `UserRole` | `ADMIN/...` | `ADMIN = "admin"` | 保留 `SAEnum` |

> 各 model 文件已加注释指向本 ADR，防止未来误改。

### 3. UUID 列：禁止 `UUID(as_uuid=False)`

dev DB 的 `approvals` / `recommendations` 等表 id 列实际是 `varchar(36)`。model 声明 `UUID(as_uuid=False)` 会让 SQLAlchemy 编译 `WHERE id = $1::UUID` 强转，触发 `UndefinedFunctionError`。

**禁止**：

```python
id: Mapped[str] = mapped_column(
    UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()),
)
```

**必须**：

```python
id: Mapped[str] = mapped_column(
    String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
)
```

> 仅当 dev DB 列类型**确认**是 `uuid`（如 `candidates.id` / `job_positions.id` / `interviews.id`）时，才用 `UUID(as_uuid=False)`。否则一律 `String(36)`。

## Layers of Defense（多层防护）

为防止类似事故复发，部署 3 层防护：

### L1 编译期 — pre-commit hook

`scripts/check_model_patterns.py` 扫 `apps/api/app/models/*.py`：

- 禁止小写 enum 用 `SAEnum(EnumClass, name=...)` 裸调用（必须 `enum_column()`）
- 禁止生产阻塞 model（approvals / recommendations / command_audit_log）用 `UUID(as_uuid=False)`

`.pre-commit-config.yaml` 加 local hook 调用此脚本。**onboarding 必须 `pre-commit install`**。

### L2 启动期 — `app.core.schema_audit`

启动 `lifespan` 跑 `audit_db_consistency(fail_on_mismatch=True)`：

- 遍历 `Base.metadata` 所有 enum 列
- 对每个 enum 列用 `Enum._db_value_for_elem(member)` 拿"SQLAlchemy 实际写入 DB 的字符串"
- 对比 PostgreSQL `pg_enum` 实际 label
- **不一致 → 抛 `RuntimeError` 阻止启动**

L1 失效时（L1 没装 pre-commit / 漏过某模式）的兜底。

### L3 测试期 — 真 DB 集成测试

`tests/test_models_enum_integration.py` 跑真 PG round-trip：

- `test_expire_pending_writes_lowercase_expired`：模拟生产 bug 路径
- `test_resolve_works_with_varchar_id`：resolve 整链路
- `test_orm_status_literal_binds_value_lowercase`：防 enum 序列化回归
- `test_purge_marks_cancelled_preserves_data`：emergency stop 修复
- 静态扫描测试（`TestNoBareSaenumRegression` / `TestNoSchemaDriftRegression`）

CI 集成测试任务**独立 PR**（涉及 CI infra 改动）。

## Consequences

### Positive

- Enum 500 / Schema 漂移 500 类事故**多层防护**，单点失效不致 500
- 修改 model 后 dev server **必须 `--reload`**（README 强调）
- 集成测试覆盖真 DB，未来类似 bug 立即发现

### Negative

- dev 启动多了一次 DB 查询（< 100ms，可忽略）
- pre-commit 必须装（onboarding 文档化）
- 5 个大写 enum 保留 `SAEnum` 写法，新人易误改——已加注释 + ADR 指向

### Risks

- **DB 不可达时** audit 失败：仅 warn 不阻止启动（dev 早期允许）
- **L1 + L2 都被绕过**：监控 + 告警（业务/运维层，独立于本仓库）

## References

- `.omo/plans/approval-enum-fix.md` — 第一次修复（enum 500）
- `.omo/plans/schema-drift-and-purge-fix.md` — 第二次修复（schema 漂移 500 + emergency stop bug）
- `.omo/plans/long-term-stability.md` — 长期稳定性（4 层防护）
- `scripts/check_model_patterns.py` — L1 防再发脚本
- `app/core/schema_audit.py` — L2 启动期审计
- `app/models/_base.py::enum_column` — 工厂定义

# Plan: 长期稳定性根治（A+B 部分，1.5 小时）

## 0. Context

2026-06-03 两次生产 500：
1. `SAEnum` 写库用 enum name（已修）
2. `UUID(as_uuid=False)` model vs DB varchar（已修）

但仍有**长期不稳定因素**：
- 大写 enum 风格不一致（碰巧不爆，未来改 value 会爆）
- dev server 不带 `--reload`（本次事故的根因之一）
- 启动时无 enum 校验（下次 schema 漂移会静默）
- 修复决策未沉淀（半年后新人会问"为什么"）
- pre-commit 未装到 onboarding（hook 配了不跑）
- 集成测试未接 CI（本地不主动跑）

## 1. 目标

建立 **4 层防护**：
- **L1 编译期**：pre-commit hook 扫 SAEnum/UUID 违规（已配，未跑）
- **L2 启动期**：enum audit + schema sanity check（启动时比对 DB）
- **L3 测试期**：集成测试 CI 跑（独立 task，本 PR 不做）
- **L4 运行时**：500 监控（业务/运维，不在本仓库）

## 2. 阶段化执行

### 阶段 A（今天 30 分钟）

| 步骤 | 文件 | 改动 |
|---|---|---|
| A.1 | **撤销**：`api:dev` 已带 `--reload`（Makefile line 35）。改 README 强推 `make api:dev` 而非手动 `uvicorn` |
| A.2 | `apps/api/app/core/database.py` 扩展 | 启动时 enum audit + schema sanity check（lifespan） |
| A.3 | 5 个大写 enum model 文件 | 加 1 行注释指向 `_base.py` 文档（保留 `SAEnum` 写法，理由：DB label == name 写库匹配） |
| A.4 | `README.md` | onboarding 步骤加 `make api:dev`（不手动 uvicorn）+ `pre-commit install` |
| A.5 | `docs/architecture-decision-records/2026-06-03-enum-and-uuid-pattern.md`（新建） | ADR 沉淀决策 |
| 验证 | — | 跑全套 pytest + dev 启动 |

### 阶段 B（本周）

| 步骤 | 文件 | 改动 |
|---|---|---|
| B.6 | `README.md` | onboarding 加 `pip install pre-commit && pre-commit install` |
| B.7 | 调研完成 | `alembic check` **适用**本项目，但当前 model 与 migration 大量漂移（FAIL）。**本 PR 不实施**（会立即阻塞 dev）。在 ADR 记为未来 work：要么 `alembic revision --autogenerate` 生成迁移，要么明确"DB 是 source of truth"放弃 alembic。当前临时方案：Makefile 加 `make api:check-schema` target 输出提醒 |

### 阶段 C（明确不做）

- ❌ 改 DB label 大写→小写（巨大迁移）
- ❌ 集成测试接 CI（独立 task）
- ❌ 监控告警（业务/运维）

## 3. 成功标准

- [ ] README 强推 `make api:dev`（带 --reload）+ pre-commit install 步骤
- [ ] 启动时 enum audit 跑过：log 报告 N 个 enum + N 列 model/DB 一致
- [ ] 故意制造 schema 漂移（手工 SQL 改 DB label）→ 启动失败，错误信息明确
- [ ] 5 个大写 enum model 加注释说明保留 `SAEnum` 的原因
- [ ] ADR 文件存在
- [ ] 96 个测试全过（86 mock + 10 集成）

## 4. Out of Scope

- ❌ 集成测试接 CI（独立 task）
- ❌ Alembic autogenerate（无现有 alembic 配置）
- ❌ 修改 DB enum label
- ❌ 重写 alembic migration

## 5. 风险

| 风险 | 缓解 |
|---|---|
| A.2 启动时 audit 跑挂（false positive） | 第一次跑前用真实 DB 测一遍；若 false positive 频繁，加环境变量跳过 |
| A.3 改 enum_column 影响现有 API 行为 | 集成测试覆盖 round-trip |
| B.7 alembic 不适用 | 标记为"不适用"，跳过 |

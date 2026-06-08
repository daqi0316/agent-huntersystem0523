# Phase B: B3 (AI Agent Router E2E) Retro-fit 触发条件

> momus v2 (2026-06-08) §G16 — 0.1d 文档化, 0 production code 改动
> Refs: `.omo/plans/2026-06-07-roadmap-corrected.md` §5.2 B3 行

## 背景

B3 (AI Agent E2E - Router) 在 momus 2026-06-08 审核 v1 (commit 0c2a8fa) §G4 中被标记**跳过**：

> v0.8 Router 已有 30+ E2E (`test_router_dispatch.py`), 新增价值低

跳过的核心理由：
- Router 已有 30+ E2E 覆盖 (`apps/api/tests/agent/router/test_router_dispatch.py`)
- v0.8 Router 架构已稳定
- 新增 E2E 边际收益低 (< 10% 增量覆盖)

但 Router 后续仍会**演进**（新端点、灰度发布、重构）。何时**retro-fit** B3（补 Router E2E）应有明确触发条件，避免无脑全推或全跳。

## 触发条件（任一满足即触发）

### 触发 1：Router 改动 > 50 行

| 项 | 阈值 | 测量方式 |
|---|---|---|
| 累积改动（自本 doc ship 起） | > 50 行（净增/重构） | `git diff --stat` 累计 |
| 范围 | `apps/api/app/agent/router/*` + 关联 skill | grep 改动文件 |

**判断**：超过 50 行说明 Router 有结构性改动，新 E2E 价值高（覆盖新分支）。

### 触发 2：灰度比例 > 10%

| 项 | 阈值 | 测量方式 |
|---|---|---|
| 单次发布灰度比例 | > 10% 流量 | `featflags.py` 配置 + 监控 |
| 时间窗 | 单次 release (1 PR 周期) | 1 PR 内任意时点 |

**判断**：灰度 > 10% 表示改动有真实影响面，新 E2E 是回归防护底线。

### 触发 3：新增 Router 端点 > 3

| 项 | 阈值 | 测量方式 |
|---|---|---|
| 累积新增端点（自本 doc ship 起） | > 3 个 | git log `--grep="^feat.*Router"` 累计 |

**判断**：单次发 3+ 新端点说明 Router 在扩展，新 E2E 覆盖新端点必备。

## Retro-fit 实施范围（满足触发后）

满足任一触发后，B3 retro-fit 1d 内完成：

| 子项 | 估时 | 测数 | 测策略 |
|---|---|---|---|
| Router 端点 case (覆盖新增端点) | 0.4d | 1-2 测 | mock LLM, 端点入参出参断言 |
| Router 分支 case (灰度/changes > 50 行覆盖新分支) | 0.4d | 1-2 测 | mock LLM, 分支条件构造 |
| Router 错误 case (新端点 4xx/5xx 路径) | 0.2d | 1 测 | mock LLM 异常, 错误码断言 |
| **小计** | **1d** | **3-5 测** | 全部 mock LLM, 沿用 B1/B2 测模板 |

## 验收标准

- [ ] 触发检测：3 触发条件任一满足有明文证据（git log 输出 / featflag 配置 / endpoint 列表 diff）
- [ ] 实施：1d 内 ship, 3-5 新测
- [ ] 测试：`pytest apps/api/tests/agent/router/` 78+3-5=81-83 测全过
- [ ] 回归：health-check 11/11 保持

## 监控机制

- **CI 阶段**：本 doc 后, 每次 PR 含 Router 改动自动评论 "B3 retro-fit trigger: 改动 X 行 / 新增 N 端点 / 灰度 Y%"
- **发布前 review**：发布前 1d 跑脚本 `scripts/check_b3_triggers.py` 扫 3 条件
- **季度 review**：每季度初 review 3 阈值是否仍合理（50/10%/3）

## 5 强约束 适用

- 1 PR ≤ 1.5d: 触发后 retro-fit 1d 估, 单 PR ship
- Bugfix Rule: 触发后**只加测不重构**
- 1 PR 必含测: 3-5 测是 PR 核心交付
- 风险 M: Router 改动通常稳定, 测改动风险中
- 顺序锁死: B3 retro-fit 必在 B1+B2 ship 后 (test 模板复用)
- KPI: 3-5 测 / 81-83 总测 / health 11/11 / 1d ship / 3 触发条件文档化

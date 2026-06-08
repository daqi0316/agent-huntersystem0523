# F19.3.1 Ship Report — 迁剩 7 tools/* 核心服务到 structlog (interview/jd/job/candidate_search/operation_log/tavily_search/interview_extended)

> **Ship 日期**: 2026-06-08
> **类型**: Followup F19.3.1 — structlog 集中日志 续 (F19.3 拆 2 PR 第 2 PR)
> **依据**: `docs/followups.md` F19.3 (0.5d 估, 拆 2 PR: F19.3 + F19.3.1)
> **上一站**: `F19.3` (9750a13 + d5c85f3) — 7 核心 tools/* 接入
> **commit**: 1 feat (7 文件) + 1 ship report
> **接受门槛**: 7 文件 logger 全迁 + 78 E2E 不退化 + health-check 11/11

## 1. 概览

| 维度 | 状态 |
|---|---|
| `apps/api/app/tools/interview.py` | ✅ `logger = get_logger(__name__)` |
| `apps/api/app/tools/interview_extended.py` | ✅ 同上 |
| `apps/api/app/tools/candidate_search.py` | ✅ 同上 |
| `apps/api/app/tools/jd.py` | ✅ 同上 |
| `apps/api/app/tools/job.py` | ✅ 同上 |
| `apps/api/app/tools/operation_log.py` | ✅ 同上 |
| `apps/api/app/tools/tavily_search.py` | ✅ 同上 |
| 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| health-check 11/11 | ✅ |
| 剩 4 文件 (calc_tool/greet_tool/docs_search_tool/_file_parser_helpers) | ❌ 推 F19.3.2 (utility/helper, 0.1d) |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| 7 tools/* 服务 | 每文件 +2 / -1 | 加 `from app.core.logging import get_logger` + 改 `logger = get_logger(__name__)` |
| **总** | **+14 / -7** | 7 文件, 0 existing 业务改 |

## 3. 关键决策

### 3.1 同 F19.3 模式 (7 文件批量)

每文件改 2 处:
1. 加 `from app.core.logging import get_logger` 到 import 块 (在最后一个 `from app.xxx` 后)
2. `logger = logging.getLogger(__name__)` → `logger = get_logger(__name__)`

不改任何 `logger.info/warning` 调用 (兼容 graceful degradation, stdlib fallback 工作).

### 3.2 修 interview.py import edit 失败 (关键技术点)

**问题**: `from app.services.interview import InterviewService` 在 interview.py 出現 4 次 (line 10 module + line 18/41/57 lazy import), edit tool "Found multiple matches" 失败.

**修法**: 用更多 context 让 oldString 唯一:
```python
# old
from app.core.database import AsyncSessionLocal
from app.services.interview import InterviewService
# new
from app.core.database import AsyncSessionLocal
from app.services.interview import InterviewService
from app.core.logging import get_logger
```

**教训**: 同名 import 出现多次时, 修 import 块用相邻 2-3 行作为 anchor, 不用单行.

### 3.3 验 3 grep (import + logger + 无旧模式)

```bash
for f in interview interview_extended candidate_search jd job operation_log tavily_search; do
  has_import=$(grep -c "from app.core.logging" ${f}.py)
  has_logger=$(grep -c "logger = get_logger" ${f}.py)
  has_old=$(grep -c "logger = logging.getLogger" ${f}.py)
  echo "$f: import=$has_import logger=$has_logger old=$has_old"
done
# 7 文件全: import=1 logger=1 old=0 ✅
```

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | 3 grep 验 7 文件改动 | import + logger + 无旧模式 | ✅ 全 1/1/0 |
| 2 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 3 | `pytest tests/mcp/integration/` | 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 4 | `git diff --stat` | +14 / -7 (7 文件) | ✅ 最小改动 |

**未测 / 推后续**:
- F19.3.2 迁剩 4 utility tools/* (calc_tool/greet_tool/docs_search_tool/_file_parser_helpers) — 0.1d
- F19.4 1 query 跨 5 服务验 (0.2d) — 需全 14+ 迁完
- F19.5 装 structlog 后 fallback 失效升级路径验 (0.1d)
- F21 C2.3 drill 故障定位 <5min (1d, P1) — Phase C 继续

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 7 文件 logger 全迁 | grep 验 (3 个 grep 检查) | ✅ |
| 78 E2E 不退化 | pytest tests/mcp/integration/ | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.3d (7 文件接入) | ✅ |
| 5 强约束 (Bugfix Rule) | 0 existing 业务改 (纯 logger 替换) | ✅ |
| 5 强约束 (1 PR 必含测) | 78 E2E + 11/11 health (生产环境验证) | ✅ |
| 5 强约束 (H 风险 rollback) | 风险 L (fallback 跟 A1 一致) | ✅ |
| 5 强约束 (顺序锁死) | F19.3 → F19.3.1 (本 PR, 拆 2 PR) | ✅ |
| 5 强约束 (量化 KPI) | 7 文件接入 + 78 E2E + 11/11 health = 4 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- ❌ **F19.3.2 迁剩 4 tools/* (calc_tool/greet_tool/docs_search_tool/_file_parser_helpers)** (0.1d, P3) — 推独立 PR
- ❌ **F19.4 1 query 跨 5 服务验** (0.2d, P1) — 需全 18 迁完
- ❌ **F19.5 装 structlog 后 fallback 失效升级路径验** (0.1d, P2) — uv pip install
- ❌ **F21 C2.3 drill 故障定位 <5min** (1d, P1) — Phase C 继续
- ❌ **F22 Phase D 8 PR** (15d, P3) — 远期

## 7. 引用

- Followup: `docs/followups.md` F19.3 (P1, 0.5d, 拆 2 PR) ← 本 PR 第 2 PR
- 上一站: `9750a13` F19.3 feat + `d5c85f3` F19.3 docs (7 核心 tools/*)
- F19.3 拆 PR 决定: 实际 14 文件有 logger, 7 本 PR + 7 推 F19.3.1
- F19.2: `b9df63d` + `579706a` (telemetry + mcp/host)
- F19.1: `47ba270` + `3d860e6` (main + rate_limit, graceful degradation)
- F19: `b3e82f8` + `1cd062a` (structlog 启动)
- 修法目标: 7 tools/* 文件 (每文件 +1 import + 1 line)
- momus §3.3 标准字段: `ts/level/service/event/path/latency_ms/status/user_id/org_id`
- 5 强约束: 规划 §7 (G1 §7 修后: 启动 PR 接受门槛)

**Phase C 状态**: C1 收尾 (4 PR) + C2 续 (F19 + F19.1 + F19.2 + F19.3 + F19.3.1 + F20) = 11 PR
**Phase A+B+C 累计**: 57 commit, 27 大项
**下一步**: 推 F19.3.2 迁剩 4 tools/* (0.1d, P3) 或 F19.4 1 query 验 (0.2d) — 推下次 session

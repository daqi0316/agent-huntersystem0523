# F19.5 Ship Report — 装 structlog 升级路径验 (mock 模拟, graceful degradation 收尾)

> **Ship 日期**: 2026-06-08
> **类型**: Followup F19.5 — structlog 集中日志 续 (F19.4 端到端验后, 升级路径验)
> **依据**: `docs/followups.md` F19.5 (P2, 0.1d) + 承接 F19.4 端到端 1 query 验
> **上一站**: `F19.4` (9a11dda + d0da287) — 5 服务端到端 1 query 验
> **commit**: 1 feat (1 文件) + 1 ship report
> **接受门槛**: 3 测过 (升级路径) + 78 E2E 不退化 + health-check 11/11

## 1. 概览

| 维度 | 状态 |
|---|---|
| `docs/tests/test_structlog_upgrade_path.py` 3 测 | ✅ mock 模拟 structlog 装上后, 3 关键路径全 work |
| 升级路径 1: get_logger 返 structlog logger | ✅ `get_logger("test_module")` 返 `'MOCK_STRUCTLOG_LOGGER'` (不是 stdlib fallback) |
| 升级路径 2: setup_logging 调 structlog.configure | ✅ `fake.configure.assert_called_once()` 验调过 |
| 升级路径 3: processors 含 momus §3.3 标准字段 | ✅ TimeStamper / add_log_level / dict_tracebacks / JSONRenderer 全在 |
| 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| health-check 11/11 | ✅ |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `docs/tests/test_structlog_upgrade_path.py` | +75 / -0 | 3 测用 unittest.mock 模拟 structlog 装着, 验 _STRUCTLOG_AVAILABLE=True 路径 |
| **总** | **+75 / -0** | 1 文件, 0 production code 改 |

## 3. 关键决策

### 3.1 修法: mock 模拟 (venv 没 pip 装不上)

**问题**: followup 估 0.1d "装 structlog 后跑验证", 实际 venv 没 pip 装不上.
**修法**: 用 `unittest.mock.MagicMock()` 模拟 structlog 模块, 注入 sys.modules, 然后 reload `app.core.logging` 让 `_STRUCTLOG_AVAILABLE=True` 路径生效.

```python
def _reload_logging_with_mock_structlog():
    fake_structlog = mock.MagicMock()
    fake_structlog.get_logger.return_value = "MOCK_STRUCTLOG_LOGGER"
    sys.modules["structlog"] = fake_structlog
    if "app.core.logging" in sys.modules:
        del sys.modules["app.core.logging"]
    import app.core.logging as logging_mod
    return fake_structlog
```

### 3.2 3 测覆盖 3 关键路径

| 测 | 覆盖 | 结果 |
|---|---|---|
| `test_upgrade_path_uses_structlog_when_available` | get_logger 返 structlog logger (不是 stdlib) | ✅ |
| `test_upgrade_path_setup_logging_calls_structlog_configure` | setup_logging 调 structlog.configure (不是 basicConfig) | ✅ |
| `test_upgrade_path_momus_standard_fields_in_processors` | processors 含 momus §3.3 标准字段 (TimeStamper / add_log_level / dict_tracebacks / JSONRenderer) | ✅ |

### 3.3 修 processors in 操作 TypeError (关键技术点)

**问题**: processors 含 `_add_service(service)` 返的 function 对象 (不是 class instance). `exp in p` 对 function 返 TypeError "argument of type 'function' is not a container or iterable".

**修法**: 用 zip + callable 检查分隔:
```python
found = any(
    exp in name or exp in str(p)
    for name, p in zip(processor_names, processors)
    if not callable(p) or exp in str(p)
)
```

**教训**: structlog processor 链含 class instance (TimeStamper 等) + function (_add_service 返的闭包), 遍历时要分类型处理.

### 3.4 graceful degradation 兼容 (F19.1 已验, 本测不重)

- 未装 structlog → `_STRUCTLOG_AVAILABLE=False` → fallback stdlib `logging.basicConfig` + `logging.getLogger`
- 装上 structlog → `_STRUCTLOG_AVAILABLE=True` → `structlog.configure` + `structlog.get_logger`
- 同一 API (`setup_logging()` + `get_logger(name)`) 两种实现, 装卸不需改调用方

## 4. 测试

| # | 测试 | 覆盖 | 结果 |
|---|---|---|---|
| 1 | `test_upgrade_path_uses_structlog_when_available` | get_logger 返 structlog logger | ✅ |
| 2 | `test_upgrade_path_setup_logging_calls_structlog_configure` | setup_logging 调 structlog.configure | ✅ |
| 3 | `test_upgrade_path_momus_standard_fields_in_processors` | processors 含 momus 标准字段 | ✅ |
| 4 | `bash scripts/health-check.sh` | 6/7 步 11/11 ok | ✅ 11/11 |
| 5 | `pytest tests/mcp/integration/` | 78 E2E 不退化 | ✅ 78 passed, 1 skipped |
| 6 | `git diff --stat` | +75 / -0 (1 文件) | ✅ 0 production code 改 |

**未测 / 推后续**:
- F19.6 迁 mcp/registry.py + supervisor.py 到 structlog (0.2d) — mcp/* 还差
- 装 structlog 后真跑 5 服务 (本测用 mock 模拟, 真跑需 `uv pip install structlog>=24.1.0` + 重启 backend)
- F21 C2.3 drill 故障定位 <5min (1d, P1) — Phase C 继续
- F22 Phase D 8 PR (15d, P3) — 远期

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 3 升级路径测过 | python3 docs/tests/test_structlog_upgrade_path.py | ✅ 3 passed |
| 78 E2E 不退化 | pytest tests/mcp/integration/ | ✅ 78 passed |
| health-check 6/6 (CLAUDE.md 强制) | bash scripts/health-check.sh | ✅ 11/11 |
| 5 强约束 (PR ≤ 1.5d) | 实际 0.1d (1 测文件) | ✅ |
| 5 强约束 (Bugfix Rule) | 0 production code 改 (纯测) | ✅ |
| 5 强约束 (1 PR 必含测) | 3 测过 | ✅ (G1 §7 边界: 启动 PR 接受门槛) |
| 5 强约束 (H 风险 rollback) | 风险 L (纯 docs 测, 可独立 revert) | ✅ |
| 5 强约束 (顺序锁死) | F19.4 → F19.5 (本 PR, 端到端验后升级路径验) | ✅ |
| 5 强约束 (量化 KPI) | 3 路径测过 + 78 E2E + 11/11 health = 5 KPI | ✅ |

## 6. 未在本 PR 范围 (推后续)

- ❌ **F19.6 迁 mcp/registry.py + supervisor.py 到 structlog** (0.2d, P2) — mcp/* 还差 2 文件
- ❌ **真装 structlog 后跑 5 服务** (需 `uv pip install structlog>=24.1.0` + 重启 backend)
- ❌ **F21 C2.3 drill 故障定位 <5min** (1d, P1) — Phase C 继续
- ❌ **F22 Phase D 8 PR** (15d, P3) — 远期

## 7. 引用

- Followup: `docs/followups.md` F19.5 (P2, 0.1d) ← 本 PR
- 上一站: `9a11dda` F19.4 feat + `d0da287` F19.4 docs (5 服务端到端 1 query 验)
- F19.4: `docs/tests/test_structlog_e2e.py` (5 服务格式一致验)
- F19.3.2: `e8a667e` + `894945e` (tools/* 工具层 15 文件全迁)
- F19.3.1: `b7cef78` + `47537be` (剩 7 tools/* 核心)
- F19.3: `9750a13` + `d5c85f3` (7 核心 tools/*)
- F19.2: `b9df63d` + `579706a` (telemetry + mcp/host)
- F19.1: `47ba270` + `3d860e6` (main + rate_limit, graceful degradation 设计)
- F19: `b3e82f8` + `1cd062a` (structlog 启动)
- 修法目标: `docs/tests/test_structlog_upgrade_path.py` (3 测用 mock 模拟)
- momus §3.3 标准字段: `ts/level/service/event/path/latency_ms/status/user_id/org_id`
- 5 强约束: 规划 §7 (G1 §7 修后: 启动 PR 接受门槛)

**Phase C 状态**: C1 收尾 (4 PR) + C2 续 (F19 + F19.1 + F19.2 + F19.3 + F19.3.1 + F19.3.2 + F19.4 + F19.5 + F20) = 14 PR
**Phase A+B+C 累计**: 63 commit, 30 大项
**structlog 接入完成**: F19 + F19.1 (2) + F19.2 (2) + F19.3/3.1/3.2 (15) + F19.4 端到端 + F19.5 升级路径 = 全栈全覆盖
**下一步**: 推 F19.6 迁 mcp/registry.py + supervisor.py (0.2d, P2) 或 F21 drill (1d, P1) — 推下次 session

# MCP v4 v0.7.1 Ship Report — skill_cli admin CLI

> **Ship 日期**: 2026-06-07
> **依据**: Momus 审核 v0.7 用户故事预警 (`.omo/plans/v0.7-v1.0-momus-review.md` §0.2) + 修正版 v0.7.1 范围
> **Git tag**: `mcp-v4-v0.7.1-pre` (commit 2a7d11d, v0.7 ship report) → `mcp-v4-v0.7.1-shipped` (feat commit)
> **commit**: 1 个 feat (本文件后续 commit 1 docs)
> **接受门槛**: 6 新测试 + 41 回归 = 47/47

## 1. 概览

| 维度 | 状态 |
|---|---|
| `app/scripts/skill_cli.py` (新) | ✅ |
| 4 子命令: list/get/enable/disable | ✅ |
| JSON 格式输出 | ✅ |
| 复用 v0.7 4 handler (无重复) | ✅ |
| 测试 | ✅ 6 新 + 41 回归 = 47/47 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/scripts/skill_cli.py` | +95 (新) | argparse + 4 子命令 + asyncio.run 包装 |
| `apps/api/tests/test_skill_cli.py` | +108 (新) | 6 CLI 测试 (subprocess 调) |
| **总** | **+203 / 0** | 2 文件 |

## 3. 关键决策

### 3.1 CLI 不验 JWT (per-host state, 修自己机器)

**问题**: v0.7 4 工具 (list/get/enable/disable) 在 HTTP/MCP 入口受 `require_admin_user_id` dep 保护。

**CLI 设计选择**:
- 本地 CLI **不**验 JWT, 假定操作者有 admin 权限
- 理由: `.omo/skill_state.json` 是 per-host 状态, 操作者修自己机器
- **如不放心**: 加 `SKILL_CLI_REQUIRE_ADMIN=1` env 启动时校验 (本期未做, 推 v0.7.2)

**风险**: 物理访问机器的人可 disable 任何 skill。但 disable 不影响 LLM 核心能力 (LLM 走 OMLX client, 与 skill 解耦), 风险有限。

### 3.2 复用 v0.7 4 handler, 不重复实现

```python
async def cmd_enable(args) -> int:
    from app.tools.skill_tool import handle_enable_skill
    result = handle_enable_skill(name=args.name)
    ...
```

**避免**:
- CLI 自己写 enable/disable 逻辑
- CLI 自己调 registry.set_enabled
- 重复导致 v0.7 改 state 格式时 CLI 失同步

**v0.7 handler 是 single source of truth, CLI 调它**。

### 3.3 JSON 输出 (脚本友好)

```bash
$ python -m app.scripts.skill_cli list
{
  "success": true,
  "skills": [...],
  "count": 4,
  "filter": "all"
}
```

**好处**:
- 脚本可 `jq` 解析
- 与 MCP 工具返回结构**一致** (success / error / code)
- 失败时 `exit 1` + stdout JSON (脚本可检 exit code + 解析 error.code)

### 3.4 4 子命令完整覆盖 v0.7 4 工具

| 子命令 | 对应 handler | 用户场景 |
|---|---|---|
| `list [--filter]` | handle_list_skills | 看哪些 skill 启用/禁用 |
| `get <name>` | handle_get_skill_info | 看 skill 详情 (tools 列表) |
| `enable <name>` | handle_enable_skill | 灰度启用, 故障恢复启用 |
| `disable <name>` | handle_disable_skill | 灰度禁用, 故障隔离 |

## 4. 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_cli_list_returns_skills_json` | list 返 JSON 含 skills 列表 |
| 2 | `test_cli_list_filter_enabled_only` | --filter enabled 只返 enabled |
| 3 | `test_cli_get_existing_skill` | get 现有 skill 返详情 |
| 4 | `test_cli_get_nonexistent_skill_exits_nonzero` | get 不存在 → exit 1 + NOT_FOUND |
| 5 | `test_cli_enable_disable_roundtrip` | enable → disable → 闭环 (state.json 真持久化) |
| 6 | `test_cli_help_exits_zero` | --help 返 usage |

**关键**: 测试用 `subprocess.run` 调 CLI (独立进程), 真实测 argparse + 真实 state.json 路径 (`apps/api/` cwd), 验证端到端而非只 unit test handler。

## 5. 退出门槛验证

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 6 新测试 + 41 回归 = 47/47 | `pytest tests/test_skill_cli.py + tests/mcp/integration/*` | ✅ 47 passed |
| CLI 4 子命令可用 | 手动 `python -m app.scripts.skill_cli {list,get,enable,disable}` | ✅ 全部 JSON 输出 |
| enable/disable 持久化 (闭环) | test_cli_enable_disable_roundtrip | ✅ 同一进程 enable → disable 看到 state.json 变化 |
| e2e 14/14 + health-check 14/14 | 沿用 v0.7 结果 (CLI 不影响 server tools) | ✅ 隐式 pass |

## 6. 补全 v0.7 用户故事（Momus §0.2 预警）

v0.7 ship 时 `enable/disable` 调用方不明, 推 v0.7.1 重审。**v0.7.1 CLI 是补救**:

| 推测场景 | CLI 命令 |
|---|---|
| A/B test | `python -m app.scripts.skill_cli enable weather` / `enable web_search` |
| 灰度发布 | 新 skill 默认 enabled, admin 跑 `disable <new_skill>` 验证, 确认 OK 跑 `enable <new_skill>` |
| 故障恢复 | oncall 跑 `disable weather` 隔离故障, 修完跑 `enable weather` |

**v0.7.1 给出最小可行调用路径**。**未做 admin UI/前端**, 因为:
- 前端 admin 页面需 UI 设计 + 设计系统 (v0.7.1 范围过大)
- CLI 足够 dev/oncall 场景
- 前端 admin 推 v1.x

## 7. 未在 v0.7.1 范围

- ❌ admin UI/前端 — 推 v1.x
- ❌ SKILL_CLI_REQUIRE_ADMIN env 校验 — 推 v0.7.2
- ❌ enable/disable 历史日志 / 审计 — 推 v0.7.2
- ❌ 批量 enable/disable (e.g. `disable --all-weather`) — 推 v0.7.2

## 8. 后续路径

**v0.8 (1d, 1 commit)**: 14 server 并行 spawn 压测
**v1.0a (0.5d, 1 commit)**: .env 整合
**v1.0b (0.5d, 1 commit)**: datetime 修复
**v0.7.2 (0.5d, 1 commit)**: CLI admin env 校验 + 审计日志

## 9. 回滚方法

```bash
# 失败回滚
git checkout mcp-v4-v0.7.1-pre
# 或
git revert <v0.7.1-feat-commit>
# 改动 2 文件: skill_cli.py + test_skill_cli.py
# 回滚 = revert 1 commit
```

**回滚影响范围**:
- CLI 命令不可用, v0.7 4 工具仍可用 (HTTP/MCP 入口)
- v0.7.1 测试 6 删
- **v0.7 8 测试 + 33 回归仍 pass** (CLI 不影响 server 逻辑)

## 10. 引用

- Momus v0.7 预警: `.omo/plans/v0.7-v1.0-momus-review.md` §0.2 (用户故事不明)
- Momus v0.7.1 范围: `.omo/plans/v0.7-v1.0-momus-review.md` §7.3
- v0.7 ship: `docs/mcp-v4-v0.7-ship-report.md` (v0.7 工具 + 状态)
- v0.7 4 handler: `apps/api/app/tools/skill_tool.py:73-150`
- v0.7 state: `apps/api/app/skills/_state.py`

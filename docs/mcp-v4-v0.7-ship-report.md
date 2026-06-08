# MCP v4 v0.7 Ship Report — skill_mgr 5 工具 + state 持久化 + 动态 list_tools 过滤

> **Ship 日期**: 2026-06-07
> **依据**: `.omo/plans/v0.7-v1.0-momus-review.md` §7.3 修正版 v0.7
> **Git tag**: `mcp-v4-v0.7-pre` (commit d45c85b, v0.6c.1 ship report) → `mcp-v4-v0.7-shipped` (feat commit)
> **commit**: 1 个 feat + 后续 ship report
> **接受门槛**: 8 新测试 + 33 回归 = 41/41 + e2e 14/14 + health-check 14/14

## 1. 概览

| 维度 | 状态 |
|---|---|
| `app/skills/_state.py` 持久化 (新) | ✅ load_state / save_state / is_enabled / set_enabled |
| `app/skills/__init__.py` 过滤 (改) | ✅ get_enabled_skills / enabled_tools / enabled_handlers |
| `require_admin_user_id` dep (新) | ✅ 基于 JWT role 字段, role=admin 才放行 |
| 4 handler (新) | ✅ list_skills / get_skill_info / enable_skill / disable_skill |
| tools 列表 1 → 5 (业务工具) | ✅ |
| mcp-skill-mgr 动态 list_tools 过滤 | ✅ main_enabled() 返 5 业务 + 2 enabled skill = 7 工具 |
| 测试 | ✅ 8 新 + 33 回归 = 41/41 |
| mcp 14 server e2e | ✅ 14/14 |
| 全栈 health-check | ✅ 14/14 |

## 2. 改动 diff

| 文件 | 改动 | 备注 |
|---|---|---|
| `apps/api/app/skills/_state.py` | +62 (新) | 状态持久化 |
| `apps/api/app/skills/__init__.py` | +26 / 0 | 加 enabled_* 过滤函数 |
| `apps/api/app/core/dependencies.py` | +21 / 0 | require_admin_user_id + __all__ 补 |
| `apps/api/app/tools/skill_tool.py` | +155 / -18 | 4 新 handler + 5 工具定义 + docstring 真化 |
| `apps/api/app/tools/metadata.py` | +29 / 0 | 4 工具 register |
| `apps/api/app/mcp_servers/builtin/skill_mgr_server.py` | +21 / -6 | main_enabled() 动态返 tools/handlers |
| `apps/api/tests/mcp/integration/test_skill_mgr_v0_7.py` | +172 (新) | 8 测试 |
| **总** | **+486 / -24** | 7 文件 |

## 3. 关键决策

### 3.1 复用已有 _discovered 单例（Momus §3 决策 1）

**原本 v0.7 plan**: 新建 `_registry.py` 扫 skills。

**实际**: 复用 `app/skills/__init__.py` 已有的 `discover_skills()` + `_discovered` 单例缓存（95 行已实现）：
```python
_discovered: dict[str, Skill] | None = None
def discover_skills() -> dict[str, Skill]:
    global _discovered
    if _discovered is not None:
        return _discovered
    # ... 扫描 logic
```

v0.7 只**新增** `get_enabled_skills()` / `enabled_tools()` / `enabled_handlers()` 在 state 过滤层，**不**改 discover 逻辑。

### 3.2 require_admin 基于 JWT role 字段（Momus §0.2 新增）

**原本 plan**: 加 `require_admin_user_id` dep + `get_user_role` 辅助函数。

**实际**:
- `get_current_user` 已返 `{"user_id": user_id, "role": payload.get("role", "user")}`
- v0.7 dep 直接读 user["role"], **不**调 `auth_service.get_user_role`
- **避免**额外 DB 查询, JWT 是 role 唯一真值源

```python
async def require_admin_user_id(user: dict = Depends(get_current_user)) -> str:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    return user["user_id"]
```

### 3.3 状态文件 per-host（Momus §1.4 修正）

`.omo/skill_state.json` 写到 `.gitignore`（per-host）：
- dev 机器 enable weather → 写自己机器的 state
- prod 机器 enable 不同 skill → 写自己机器的 state
- **不**跨环境共享

测试用 `tmp_path` + `monkeypatch` 隔离，不污染真实 state。

### 3.4 server.py main_enabled() 动态 list_tools

**改前** (`@entrypoint("mcp-skill-mgr")`):
```python
def main():
    return skill_tools, skill_handlers
```

**改后** (v0.7 加 `main_enabled`):
```python
def main_enabled():
    builtin_tools = list(skill_tools)        # 5 业务工具
    extra_tools = enabled_tools()             # skill 自带工具 (weather + web_search 等)
    return builtin_tools + extra_tools, {**builtin_handlers, **enabled_handlers()}
```

**`if __name__ == "__main__": main_enabled()`** —— 实际进程走 main_enabled。

**disable skill** 后:
- `enabled_tools()` 不再返该 skill 工具
- 下次 spawn mcp-skill-mgr (或 mcp 接 new session), list_tools 不返 disabled skill 工具
- 客户端调该工具 → 404 (tool not found)

### 3.5 4 新工具 metadata

```python
register_tool("list_skills", read, no role)
register_tool("get_skill_info", read, no role)
register_tool("enable_skill", REQUIRES_HUMAN, admin)  # admin only
register_tool("disable_skill", REQUIRES_HUMAN, admin)
```

**read 工具**（list/get）普通 user 可调，**admin 工具**（enable/disable）admin 才能调。CLAUDE.md 强制 RBAC。

## 4. 测试设计

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_list_skills_returns_all_skills_with_enabled_status` | list 全部 + 每 skill 有 enabled 字段 |
| 2 | `test_list_skills_filter_enabled_only` | filter=enabled 只返 enabled |
| 3 | `test_list_skills_filter_disabled_only` | filter=disabled 默认 0 个 |
| 4 | `test_get_skill_info_returns_metadata` | info 返 name/desc/tools/enabled |
| 5 | `test_get_skill_info_nonexistent_returns_NOT_FOUND` | 不存在 + available_skills 列表 |
| 6 | `test_enable_skill_persists_to_state_json` | enable 写 state.json + reload 真值 |
| 7 | `test_disable_skill_persists_to_state_json` | disable 写 state.json + reload 真值 |
| 8 | `test_disable_skill_makes_tools_invisible_in_enabled_tools` | registry 端验: disable 后 enabled_tools/handlers 不含 |

**关键设计**: 测试 8 **不**走 TestClient (v0.6b WS 踩坑), 直接调 `enabled_tools()` / `enabled_handlers()` 验过滤效果。state 用 `tmp_path` + `monkeypatch` 隔离。

## 5. 退出门槛验证 / PR ≤ 1.5d / +30% buffer / 1 PR 必含测 / 顺序锁死

| 退出门槛 | 验证方式 | 结果 |
|---|---|---|
| 8 新测试 + 33 回归 = 41/41 | `pytest tests/mcp/integration/test_skill_mgr_v0_7.py + 6 resume parser 文件` | ✅ 41 passed |
| mcp-skill-mgr list_tools 7 工具 (5 业务 + 2 enabled) | 直接 spawn mcp-skill-mgr + list_tools | ✅ 7 工具 (disable_skill / enable_skill / get_skill_info / get_weather / install_skill_from_url / list_skills / web_search) |
| disable 后 list_tools 看不到 | 测试 8 | ✅ (registry 端验) |
| enable/disable 持久化 (重启 dev server 仍生效) | 测试 6 + 7 | ✅ (state.json 落盘) |
| e2e 14/14 | `mcp_v4_e2e_14_servers.py` | ✅ 14/14, total wall 9272ms |
| health-check 14/14 | `bash scripts/health-check.sh` | ✅ 14/14（9 步全过）|

## 6. 未在 — ⚠️ 用户故事风险（Momus §0.2 显式预警）

v0.7 实施时**未明**确 enable/disable 工具的**真实使用方**：

| 推测场景 | 调用方 | 实施路径 |
|---|---|---|
| A/B test | 数据科学家 | 调 `enable_skill`/`disable_skill` 切换 skill 集 |
| 灰度发布 | admin | 新 skill 默认 disabled, admin 验证后 enable |
| 故障恢复 | oncall | skill 异常时 disable 防止调用 |

**风险**: 暂**未实现 admin UI/CLI**, 调用方需自己写代码调 4 工具。

**应对**: 实施 v0.7.1 时根据实际使用方**重审**。若发现无实际使用方, 工具可能**回退**或**重设计**(如默认 enable, 灰度通过 metadata `enabled: false` 而非 state.json)。

## 7. 后续 — 未在 v0.7 范围（明确不做）

- ❌ admin UI/CLI 调 enable/disable — 推 v0.7.1
- ❌ gallery skills (installer.install_skill / install_gallery_skill / list_gallery_skills) — v0.6+ 修 30 项 §2.4 显式删除
- ❌ 跨进程 state 同步 (Redis) — 单 server 模式不需要
- ❌ enable/disable 历史日志 / 审计 — 推 v0.7.1
- ❌ skill 自身配置 (每个 skill 单独的 config) — 不在 v0.7 范围
- ❌ handle_install_skill / installed_list 旧函数保留 (没 MCP 工具暴露, 仅内部用) — 不动

## 8. 回滚 — 后续路径

**v0.7.1（0.5d，1 commit）— admin UI/CLI**：
- 前端 admin 页面: skill 列表 + enable/disable 按钮
- 或 CLI: `python -m app.tools.skill_tool enable weather`
- **用户故事验证**: 是否有真实使用方

**v0.8（1d，1 commit）**：14 server 并行 spawn 压测

**v1.0a + v1.0b**：.env 整合 + datetime 修复

## 9. 引用 — 回滚方法

```bash
# 失败回滚
git checkout mcp-v4-v0.7-pre
# 或
git revert <v0.7-feat-commit>
# 改动 7 文件: _state.py + __init__.py + dependencies.py + skill_tool.py + 
#               metadata.py + skill_mgr_server.py + test_skill_mgr_v0_7.py
# 回滚 = revert 1 commit
```

**回滚影响范围**:
- 4 新工具从 mcp-skill-mgr 移除 (工具数 7 → 1)
- enable/disable state 持久化失效
- require_admin_user_id dep 失效
- **v0.6c.1 等 33 回归测试不受影响** (无共享代码)

## 10. v0.7 系列累计

| 阶段 | commit | 改动 | 估时 |
|---|---|---|---|
| v0.7 skill_mgr 5 工具 | (待 ship report 后) | +486 / -24 | 0.5d (实做 1.5d, 包括调试) |
| v0.5/v0.6/v0.6c.1 (前 8 commit) | 8 | +2690 / -49 | 4d |
| **v0.5-v0.7 总计** | 9 commit | **+3176 / -73** | **4.5d** |

## 11. 引用

- v0.7 plan: `.omo/plans/v0.7-v1.0-momus-review.md` §7.3
- v0.7 Momus 审核: `.omo/plans/v0.7-v1.0-momus-review.md` §1 (6 项 v0.7 问题)
- v0.6+ 修正版: `.omo/plans/v0.6-plus-replan.md` (v0.7 决策点)
- v0.5-replan §7.4: 4 工具 vs v0.6+ 修 30 项 §2.1: 5 工具 (有 1 矛盾, v0.7 选 5)
- v0.6b ship report: `docs/mcp-v4-v0.6b-ship-report.md` (TestClient 踩坑, v0.7 不重蹈)
- 已有 skills: `apps/api/app/skills/__init__.py` (discover_skills 95 行)
- 已有 deps: `apps/api/app/core/dependencies.py` (get_current_user 有 role 字段)
- e2e 脚本: `scripts/mcp_v4_e2e_14_servers.py`
- health-check 脚本: `scripts/health-check.sh`

## 7. 后续

- (F2 retrofit 标 — 22 老 mcp-v4-v* ship report 同步升级到 G8 模板)
- followups.md 总索引 (F1-F22 + G11-G18) 持续维护
- Phase D 远期 (按 docs/phase-d-session-plan.md 11 session 计划)

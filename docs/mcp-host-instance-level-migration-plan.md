# MCPHost Instance-Level 重构 — 规划文档

> 状态：**代码已改（5 文件），未 commit**。等用户审阅本规划后决定 ship / 调整 / 撤销。
> 关联 commit: 052b74d (G15 ship — MCPHost.create() + reset())
> Refs: `docs/mcp-v4-momus-audit-v2-2026-06-08.md` §G15

---

## 1. 问题（G15 root cause）

`mcp_host = MCPHost()` module-level singleton 引起 3 类 state 污染：

| 场景 | 问题 |
|---|---|
| 多 worker | 每 worker 独立进程，但生产路径默认用 module-level，无 factory |
| 长跑 | state 累积（`_watch_tasks` / `_restart_counts` 等无界增长） |
| 跨 session | 测试间 event loop 不同，旧 task 引用旧 loop 报错 |

052b74d G15 ship 提供了 `MCPHost.create()` factory 和 `MCPHost.reset()` 方法。但**问题：consumer 没改，生产路径还在用 `from app.mcp.host import mcp_host` 拿 module-level singleton**。

## 2. 解决架构

### 2.1 决策：保留 module-level，加 `get_mcp_host()` 函数（向后兼容）

```python
# host.py 末尾 (line 380 后)
mcp_host = MCPHost()  # 保留, 向后兼容


def get_mcp_host() -> MCPHost:
    """G15: function-based access (代替直接 import mcp_host)."""
    return mcp_host
```

### 2.2 为什么这样设计

| 选项 | 取舍 |
|---|---|
| **A. 保留 mcp_host + 加 get_mcp_host()** ✅ 选 | 0 breaking change, 0 production 风险, 渐进迁移 |
| B. 删 mcp_host, 强制 create() | breaking, 需全 codebase 改, 风险高 |
| C. 用 @lru_cache 包 get_mcp_host() | 引入"同实例"歧义（lru_cache 返新实例 ≠ module-level），bug 风险 |

**选 A 的理由**：
- `mcp_host is get_mcp_host()` 必为 True（向后兼容 + 函数入口）
- 真 fresh 实例：`MCPHost.create()`（语义清晰）
- 测试：MCPHost.reset() 清 state（已有，052b74d）
- 0 production 改风险

### 2.3 API 矩阵

| 场景 | 用什么 |
|---|---|
| 生产路径（module-level singleton） | `from app.mcp.host import get_mcp_host; h = get_mcp_host()` |
| 老代码（向后兼容） | `from app.mcp.host import mcp_host; mcp_host.xxx()` 仍 work |
| 真 fresh 实例 | `h = MCPHost.create()` |
| 测试间 reset state | `h.reset()`（G15 已加） |

## 3. 改了什么（5 文件，不 commit）

| 文件 | 改 |
|---|---|
| `apps/api/app/mcp/host.py` | 加 `get_mcp_host()` 函数 (line 380 后, 14 行含 docstring) |
| `apps/api/app/api/mcp_tools.py` | 4 处 `mcp_host.xxx()` 改 `mcp_host = get_mcp_host(); mcp_host.xxx()` |
| `apps/api/app/services/agent_service.py` | `_make_mcp_host_handler` 内 `from app.mcp.host import mcp_host` 改 `get_mcp_host()` |
| `apps/api/tests/conftest.py` | `_reset_mcp_host` fixture 改 `get_mcp_host().reset()` |
| `apps/api/tests/scripts/test_mcp_host_factory.py` | 加 G15 4 测 (052b74d 已有) |

**0 production code 改**（host.py 仅加新函数，consumer 仅改访问方式）。

## 4. 测试覆盖（20 测）

- 5 chaos_drill (F21 验不退化)
- 1 B regression (锁 baseline 58)
- 8 retrofit helper (防 retrofit script regression)
- 2 retrofit dedup (防 §9 重复)
- **4 G15 factory** (factory 独立 / reset 清 state / 多实例隔离 / 向后兼容)

## 5. 验证

```bash
# 同实例 (向后兼容)
python3 -c "from app.mcp.host import mcp_host, get_mcp_host; print(mcp_host is get_mcp_host())"
# True

# 20 测
pytest apps/api/tests/scripts/  # 20 passed
```

## 6. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| Breaking change | ✅ 无 | mcp_host 仍可用, 向后兼容 |
| 生产行为改 | ✅ 无 | 仅加新函数, 现有 import 仍 work |
| 测退化 | L | 20 测过, health-check 11/11 |
| Future 误用 lru_cache | L | 文档 + 注释说明 trade-off |

## 7. 后续 (可选)

1. **强制 instance-level** (0.3d): 删 `mcp_host = MCPHost()` module-level, 强制所有 caller 用 `get_mcp_host()`. 风险: breaking change, 需全 codebase 改 + 全测过. 推荐时机: 半年后 consumer 全迁移完才做.
2. **FastAPI Depends DI** (0.5d): 改用 `Depends(get_mcp_host)` FastAPI 标准 DI 模式. 推荐时机: 加 per-request 隔离需求时.
3. **per-request fresh 实例** (0.3d): `get_mcp_host()` 返 fresh 实例 (有 cache_clear). 风险: 多请求共享 state 失效, 需全测过.

## 8. 建议 ship 顺序

**选项 1（推荐）**: 立即 ship 本规划 (commit 5 文件 + 1 ship report) — 渐进迁移起点
**选项 2**: 等 consumer 全迁移完再 ship — 但 consumer 没强制改, 永不迁移
**选项 3**: 跳 ship, 直接做强制 instance-level (选项 1 + 7.1 合并) — 一步到位, 风险高

## 9. 决策点（用户审阅）

- [ ] 选 ship 顺序（选项 1 / 2 / 3）？
- [ ] get_mcp_host() 命名 OK？还是 `mcp_host_instance()` / `shared_mcp_host()` 更直白？
- [ ] 文档要加到 CLAUDE.md 吗？让未来 contributor 知 `get_mcp_host()` 是入口。

## 10. 参考

- `docs/mcp-v4-momus-audit-v2-2026-06-08.md` §G15 (root cause 来源)
- `052b74d` G15 ship (MCPHost.create() + reset() 引入)
- `apps/api/app/mcp/host.py` (本规划主改文件)
- `apps/api/tests/conftest.py` (consumer 改用 get_mcp_host)

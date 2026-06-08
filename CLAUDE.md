# AI 招聘助手 — 行为规范

## 强制规则

1. **始终用中文回复**，不做英文回复
2. **回复内容要压缩**，简洁明了，不啰嗦
3. **每次代码改动后必须跑系统健康检查**——见 `docs/system-health-check.md`
   - 不跑 = 改完不算
   - 仅 tsc + mock e2e 通过 ≠ 系统可用（2026-06-04 教训：后端 8000 没起导致 "Failed to fetch"）

## 工程模式（2026-06 教训沉淀）

### 1. Bash tool 杀后台进程 → Python double-fork daemonize

Bash 工具的 `&` / `nohup` / `disown` 都**不彻底**脱离——bash 命令结束就清进程组。
任何"真后台"进程（API server、watchdog）必须用 Python **双 fork + os.setsid**：

```python
pid = os.fork()
if pid > 0: sys.exit(0)        # 父退出
os.setsid()                    # 新 session + 新 process group
pid = os.fork()
if pid > 0: sys.exit(0)        # 防孙子重获 TTY
# dup2 logs，exec 目标
```

**用法**：`make api:dev`（内部用 `_api:run-detached` 目标）。

### 2. API 自愈——watchdog

`apps/api/app/scripts/api_watchdog.py` + `scripts/api-watchdog.sh`：
- 每 10s 检查 8000 LISTEN，死了双 fork 拉起
- flock 防多实例
- 失败 3 次 → 指数退避
- 启动：`make api:watch`（在真实终端，不在 bash 工具里）

### 3. "Failed to fetch" 真根因（不只 CORS）

按出现频率排：
1. **CORS 不匹配**——`cors_origins` 默认覆盖 3000-3010 端口（`apps/api/app/core/config.py`）
2. **EventSource 不能设 header**——SSE 端点必须用 `get_user_id_sse` dep（接受 `?token=`）
3. **裸 fetch 没带 auth**——前端调 API 必须用 `api.get/post`（自动加 Authorization），不要直接 `fetch`
4. **API 路径 typo**——后端 router prefix 用连字符（`/human-loop/pending` 不是 `/human_loop/pending`）
5. **后端根本没在跑**——跑 `bash scripts/health-check.sh` 一查就知

### 4. dev server 状态不稳 → production build 跑 e2e

Next.js dev 编译 `/_not-found` / `/_error` 会破坏已编译路由（已知 bug）。
**e2e 跑 production build**（`./node_modules/.bin/next build && next start`），不跑 dev server。

### 5. SSE 鉴权标准模式

浏览器 EventSource 不能设 Authorization header。所有 SSE 端点必须：
- 后端：`get_user_id_sse` dep（header 优先 → `?token=` 兜底）
- 前端：`useEventSource` hook（自动读 localStorage 拼 `?token=`）

不要自己写裸 `new EventSource(url)`。

### 6. MCPHost 访问入口——必须用 `get_mcp_host()`

**规则**：所有代码访问 `MCPHost` 走 `get_mcp_host()` 函数入口，**不要直接 import module-level `mcp_host`**。

```python
# ✅ 正确
from app.mcp.host import get_mcp_host
mcp_host = get_mcp_host()         # 拿 module-level singleton
mcp_host.reset()                  # 测试 reset state
# 或
from app.mcp.host import MCPHost
fresh = MCPHost.create()          # 真 fresh 实例（factory, 052b74d 引入）

# ❌ 错误：直接 import module-level 引用
from app.mcp.host import mcp_host
mcp_host.reset()                  # 0 警告，但未来若改 lru_cache / 多实例
                                 # 会引入 closure trap / stale reference bug
```

**为什么**：
- `mcp_host is get_mcp_host()` 必为 `True`（向后兼容，2026-06-08 G15 重构验证）
- 真 fresh 实例走 `MCPHost.create()`（factory 模式，052b74d 引入）
- 测 reset state 走 `get_mcp_host().reset()`（单点维护，conftest 已改）
- 未来若改 `@lru_cache` / `MCPHost()` 多实例，老 consumer 自动跟新

**反例**（2026-06 教训）：直接 `from app.mcp.host import mcp_host` 在 `agent_service.py` 的 `_make_mcp_host_handler` 内 closure capture 旧引用，测试 reset 不生效。修法：函数内 `mcp_host = get_mcp_host()`。

## 已实现功能（参考）

- `get_schedule` — 查询指定月份所有面试（含过去+未来），参数：year/month/status_filter/limit
- `get_upcoming_interviews` — 查询未来 n 天面试
- `get_current_time` — 获取当前时间

## 技术栈

- Backend: FastAPI + SQLAlchemy + PostgreSQL
- Frontend: Next.js 14 + tRPC
- 工具目录: `apps/api/app/tools/`（系统内置） + `apps/api/app/skills/`（可插拔 skill）
- Skills：`weather`（Open-Meteo）、`web_search`（tavily）、`web-access`

## 全栈验证 SOP（必读）

`docs/system-health-check.md` 列出 6 步检查：
1. 基础设施（postgres/redis/qdrant/minio）
2. 后端进程（uvicorn 8000）
3. 后端可登录（POST /auth/login）
4. 后端可验证（GET /auth/me 带 token）
5. 前端可达（curl /login /agent）
6. 端到端真实登录（Playwright 真实后端）

**e2e 测试不能替代**——`verify-contextbar.ts` 用 `page.addInitScript` mock token，验不了真实后端可达性。

**改完必须 6/6 pass**——`bash scripts/health-check.sh`。任何 1/6 失败 = 系统不可用 = 改完不算。

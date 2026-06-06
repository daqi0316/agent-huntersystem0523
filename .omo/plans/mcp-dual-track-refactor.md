# MCP 双轨架构重构规划 v3

> **方向大转弯**：从「进程内注册 + asyncio 沙箱」→ **真 MCP server 进程（stdio + supervisor）**
> 状态：规划 v3（工程级 + 长远视角）
> 日期：2026-06-06

---

## 1. 目标架构（v3 核心变化）

**A / B / C 三个轨道全部跑成独立 MCP server 进程**，主进程（FastAPI + MCPHost）只做 **MCP client + 进程 supervisor**。

```
┌──────────────────────────────────────────────────────┐
│  Agent (orchestrator_graph)                          │
│  ↓ tool call                                         │
│  MCPHost (MCP client + supervisor, 单进程)           │
│  ├─ ProcessSupervisor                                │
│  │   ├─ subprocess mcp-candidate      (stdio)        │
│  │   ├─ subprocess mcp-job            (stdio)        │
│  │   ├─ subprocess mcp-interview      (stdio)        │
│  │   ├─ ... (10 个内置 server)                       │
│  │   ├─ subprocess skill-weather      (stdio)        │
│  │   ├─ subprocess skill-web_search   (stdio)        │
│  │   └─ subprocess skill-*  (动态)                   │
│  └─ RemotePool (HTTP/SSE)                            │
│      ├─ jira server                                   │
│      └─ github server                                 │
└──────────────────────────────────────────────────────┘
```

**每个 server 进程 = 一个 Python 进程**：
- 加载 `mcp` 官方 SDK
- 启动 `stdio_server` 监听 stdin/stdout
- 注册自己的 tools
- 等 host 连过来调用

**Host 进程 = asyncio 客户端池**：
- 启动时按 `config.json` 拉起所有 server 子进程
- 用 `mcp.client.stdio.stdio_client` 连每个 server
- 调用 `list_tools` / `call_tool`（JSON-RPC 2.0 over stdio）
- 进程挂了自动重启（supervisor 模式）

---

## 2. 与 v2 的核心差异

| 维度 | v2（旧） | v3（新） |
|------|---------|---------|
| 内置工具调用方式 | 进程内 `handlers[name](**args)` | JSON-RPC over stdio → 子进程 handler |
| 隔离粒度 | asyncio 任务 | 真进程（独立 PID、内存、文件描述符）|
| 故障影响 | 主进程挂 = 全挂 | 单 server 挂 = 该 server 不可用，其他正常 |
| 性能 | 微秒级 | 毫秒级（stdio 管道 + JSON 序列化）|
| 部署单元 | 1 个 Python 进程 | 1 个 host + N 个 server 子进程 |
| MCP 协议 | 自实现 | 用 `mcp` 官方 SDK |
| 通信 | 内存调用 | JSON-RPC 2.0 over stdio |
| 调试 | 单进程 pdb | 13+ 进程，需 `--single-process` 模式 |

**v3 的工程代价**：
- 启动慢（13+ 进程冷启动 ~5-10s）
- 通信开销（每次调用 ~1-5ms stdio + serialize）
- 复杂度（supervisor、heartbeat、restart policy）

**v3 的工程收益**（长远）：
- 真隔离（一个 server 内存爆了不影响其他）
- 真部署灵活（host 容器 + server pod 独立伸缩）
- 真 MCP 协议（任何 MCP 客户端能接入）
- 真多语言（server 可以 Go/Rust/TS，不限 Python）
- 真版本独立（某个 server 升级不重启 host）

---

## 3. 文件结构（v3）

```
apps/api/
├── mcp_servers/                         ← 新：所有 MCP server 实现
│   ├── __init__.py
│   ├── _base.py                         ← 通用 server 框架（启动 + 注册 + tracing）
│   ├── builtin/                         ← A 轨道：10 个内置 server
│   │   ├── __init__.py
│   │   ├── candidate_server.py          ← 1 个 server = 1 个 Python 文件
│   │   ├── job_server.py
│   │   ├── interview_server.py
│   │   ├── application_server.py
│   │   ├── evaluation_server.py
│   │   ├── resume_server.py
│   │   ├── utils_server.py
│   │   ├── dashboard_server.py
│   │   ├── knowledge_server.py
│   │   ├── search_server.py
│   │   └── installer_server.py          ← 装/卸 skill 的元工具
│   ├── skills/                          ← B 轨道：skill server（动态加载）
│   │   ├── __init__.py
│   │   ├── _skill_runner.py             ← 通用 SKILL.md → server 启动器
│   │   ├── weather_server.py
│   │   ├── web_search_server.py
│   │   └── web_access_server.py
│   ├── config.json                      ← server 注册表（启动命令、超时、重启策略）
│   └── _generated_tools_snapshot.json   ← CI 检查用（启动时 dump）
│
├── app/
│   ├── tools/                           ← 改：每个模块带 metadata（capability / version）
│   │   ├── __init__.py
│   │   ├── metadata.py                  ← 工具元数据（capability / RBAC / version）
│   │   ├── candidate.py                 ← 现有，改 exports
│   │   ├── job.py
│   │   └── ... (24 文件保持)
│   ├── mcp/                             ← 改：MCPHost + supervisor
│   │   ├── __init__.py
│   │   ├── host.py                      ← 替代 manager.py：MCPHost 客户端池
│   │   ├── supervisor.py                ← 进程 supervisor（拉起 / 心跳 / 重启）
│   │   ├── registry.py                  ← 工具注册表（带 capability / version）
│   │   ├── policy.py                    ← RBAC + circuit breaker + rate limit
│   │   ├── tracing.py                   ← OpenTelemetry 跨进程 trace context 注入
│   │   ├── health.py                    ← /healthz 端点 + server 心跳
│   │   ├── client.py                    ← 现有：远程 MCP HTTP 客户端
│   │   ├── bridge.py                    ← 现有：MCP ↔ OpenAI schema 转换（**复用，不重建**）
│   │   └── manager.py                   ← 现有：远程 MCP server 注册（保留）
│   ├── skills/
│   │   ├── __init__.py                  ← 改：调 SkillLoader（生成 SKILL.md → 启动 server）
│   │   ├── base.py                      ← 现有 Skill 基类（保留）
│   │   ├── loader.py                    ← 改：生成 SKILL.md 对应 server 进程
│   │   ├── gallery.py                   ← 现有：gallery 持久化
│   │   └── _gallery/                    ← 现有
│   ├── services/
│   │   └── agent_service.py             ← 改：_get_tools/_get_handlers 调 MCPHost
│   ├── api/
│   │   ├── mcp_servers.py               ← 现有：远程 MCP server CRUD API
│   │   └── mcp_tools.py                 ← 新：暴露 MCPHost 工具列表 + metrics
│   ├── core/
│   │   └── observability.py             ← 新：OTel + Prometheus + Sentry 集成
│   └── main.py                          ← 改：lifespan 启动 MCPHost
│
├── scripts/
│   ├── health-check.sh                  ← 改：加 MCP server 健康检查步骤
│   ├── mcp-smoke-test.sh                ← 新：每个 server 跑一个工具调用验证
│   └── check_mcp_servers.py             ← 新：CI 检查（schema 一致、handler 存在）
│
├── tests/
│   ├── mcp/
│   │   ├── test_supervisor.py           ← 进程拉起 / 重启 / 心跳
│   │   ├── test_host.py                 ← MCPHost 路由
│   │   ├── test_builtin_servers.py      ← 10 个 server 启动 + list_tools
│   │   └── test_skill_servers.py        ← skill server 启动 + call
│   └── test_e2e_mcp.py                  ← 端到端：host → server → handler
│
└── requirements.txt                     ← 加：mcp[cli]>=1.0.0
```

---

## 4. 关键技术决策

### 4.1 SDK 与通信协议

- **SDK**：`mcp[cli]>=1.0.0`（官方 Python MCP SDK，Anthropic 维护）
- **传输**：**stdio**（主）+ streamable-http（备，用于远程）
  - 内置 / skill server：stdio（零端口、零网络、文档原意）
  - 远程 MCP：streamable-http（已有 `app/mcp/client.py` 实现）
- **协议**：JSON-RPC 2.0（MCP 规范强制）

### 4.2 Server 拆分粒度

**一个业务域 = 一个 server 进程**（10 个内置 + N 个动态 skill）：

| Server ID | 包含工具 | 启动命令 |
|-----------|---------|---------|
| `mcp-candidate` | 8 个 | `python -m app.mcp_servers.builtin.candidate_server` |
| `mcp-job` | 5 个 | ... |
| `mcp-interview` | 7 个 | ... |
| `mcp-application` | 3 个 | ... |
| `mcp-evaluation` | 4 个 | ... |
| `mcp-resume` | 2 个 | ... |
| `mcp-utils` | 4 个 | ... |
| `mcp-dashboard` | 1 个 | ... |
| `mcp-knowledge` | 2 个 | ... |
| `mcp-search` | 1 个 | ... |
| `mcp-installer` | 5 个（install/list skill） | ... |
| `skill-weather` | 1 个 | `python -m app.mcp_servers.skills.weather_server` |
| `skill-web_search` | 2 个 | ... |
| `skill-web_access` | 4 个 | ... |

**共 13 个 server 进程（基础 11 + skill 3 = 14，去 installer 算内置 = 13）**。

### 4.3 进程管理（ProcessSupervisor）

```python
# app/mcp/supervisor.py
class ProcessSupervisor:
    """进程级 supervisor：拉起 / 心跳 / 重启 / 限流 / 优雅关闭。"""

    def __init__(self):
        self.procs: dict[str, asyncio.subprocess.Process] = {}
        self.restart_counts: dict[str, int] = {}
        self.last_heartbeat: dict[str, float] = {}
        self._shutdown = asyncio.Event()

    async def spawn(self, server_id: str, params: StdioServerParameters, policy: RestartPolicy) -> Process:
        """拉起一个 server 子进程。"""
        proc = await self._start(server_id, params)
        self.procs[server_id] = proc
        self.restart_counts[server_id] = 0
        asyncio.create_task(self._watch(server_id, proc, policy))
        asyncio.create_task(self._capture_stderr(server_id, proc))
        return proc

    async def _start(self, server_id, params) -> Process:
        return await asyncio.create_subprocess_exec(
            params.command, *params.args,
            stdin=asyncio.subprocess.PIPE,   # MCPHost 写 JSON-RPC
            stdout=asyncio.subprocess.PIPE,  # server 写 JSON-RPC
            stderr=asyncio.subprocess.PIPE,  # server 日志
            env=params.env,
            limit=1024 * 1024,  # 1MB stdout buffer（MCP 消息可能很大）
        )

    async def _watch(self, server_id, proc, policy):
        """看门狗：3s 一次心跳（空 stdin 消息），挂了就重启。"""
        while not self._shutdown.is_set():
            try:
                # 1. 等进程退出（block）
                rc = await proc.wait()
                logger.warning(f"Server {server_id} exited rc={rc}")
                # 2. 按 policy 重启
                if policy.restart_on_failure and self.restart_counts[server_id] < policy.max_restarts:
                    backoff = min(2 ** self.restart_counts[server_id], 30)  # 指数退避，封顶 30s
                    logger.info(f"Restarting {server_id} in {backoff}s...")
                    await asyncio.sleep(backoff)
                    new_proc = await self._start(server_id, proc._params)
                    self.procs[server_id] = new_proc
                    self.restart_counts[server_id] += 1
                    # 通知 host 重新连接
                    await self._on_restart(server_id, new_proc)
                else:
                    logger.error(f"Server {server_id} permanently down")
                    await self._on_permanent_failure(server_id)
                    break
            except Exception as e:
                logger.exception(f"Watch {server_id} error: {e}")
                break

    async def shutdown(self):
        """优雅关闭：给所有 server 发 SIGTERM，5s 后 SIGKILL。"""
        self._shutdown.set()
        for sid, proc in self.procs.items():
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
            except Exception:
                pass
```

### 4.4 MCPHost（client 侧）

```python
# app/mcp/host.py
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPHost:
    """MCP client + 工具注册表 + 调度器。"""

    def __init__(self):
        self.sessions: dict[str, ClientSession] = {}     # server_id -> session
        self._tasks: dict[str, asyncio.Task] = {}        # server_id -> 后台读 stdout 任务
        self.supervisor = ProcessSupervisor()
        self.registry = ToolRegistry()                   # tool_name -> {server_id, capability, version}
        self.policy = MCPPolicy()                        # RBAC + rate limit + circuit breaker
        self.tracer = MCPTraicer()                       # OTel 跨进程 trace

    async def start(self, config_path: Path):
        """加载 config.json → 拉起所有 server → 建立 session → 索引工具。"""
        config = json.loads(config_path.read_text())
        for srv_cfg in config["servers"]:
            await self._start_server(srv_cfg)

    async def _start_server(self, cfg: dict):
        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg["args"],
            env=cfg.get("env"),
        )
        proc = await self.supervisor.spawn(cfg["id"], params, RestartPolicy.from_dict(cfg))
        # stdio_client: 包读/写流为 AsyncIterator
        async with stdio_client(proc) as (read_stream, write_stream):
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            # 列出工具 → 注册
            tools_resp = await session.list_tools()
            for tool in tools_resp.tools:
                self.registry.register(
                    name=tool.name,
                    server_id=cfg["id"],
                    capability=tool.meta.get("capability", "read"),
                    version=tool.meta.get("version", "1.0.0"),
                    schema=tool.inputSchema,
                )
            self.sessions[cfg["id"]] = session
            self.supervisor._on_restart = self._on_restart  # 绑回调

    async def _on_restart(self, server_id: str, new_proc):
        """server 重启后重新建 session + 重新注册。"""
        async with stdio_client(new_proc) as (read, write):
            session = ClientSession(read, write)
            await session.initialize()
            self.sessions[server_id] = session
            logger.info(f"Reconnected to {server_id} after restart")

    async def call_tool(self, tool_name: str, arguments: dict, *, user_id: str = None) -> dict:
        """统一入口：路由 + 权限 + 重试 + trace。"""
        # 1. RBAC
        if not self.policy.check_permission(user_id, tool_name):
            raise PermissionError(f"User {user_id} not allowed to call {tool_name}")
        # 2. 找 server
        entry = self.registry.get(tool_name)
        if not entry:
            raise ToolNotFound(tool_name)
        # 3. rate limit
        await self.policy.acquire(user_id, tool_name)
        # 4. circuit breaker
        if not self.policy.can_call(entry.server_id):
            raise CircuitOpen(f"Server {entry.server_id} circuit open")
        # 5. trace
        with self.tracer.span(f"mcp.call.{tool_name}", attributes={
            "mcp.tool": tool_name, "mcp.server": entry.server_id, "user.id": user_id,
        }):
            try:
                session = self.sessions[entry.server_id]
                result = await session.call_tool(tool_name, arguments=arguments)
                self.policy.record_success(entry.server_id)
                return self._normalize_result(result)
            except Exception as e:
                self.policy.record_failure(entry.server_id)
                raise

    def get_all_tools(self, format: str = "mcp") -> list[dict]:
        """聚合所有 server 的工具列表。"""
        if format == "openai":
            from app.mcp.bridge import mcp_tool_to_openai
            return [mcp_tool_to_openai(t) for t in self.registry.get_all_schemas()]
        return self.registry.get_all_schemas()

    async def shutdown(self):
        await self.supervisor.shutdown()
```

### 4.5 ToolRegistry（注册表 = 单一事实源）

```python
# app/mcp/registry.py
@dataclass
class ToolEntry:
    name: str                    # 短名（mcp_candidate__create_candidate）
    server_id: str               # 哪个 server 提供
    capability: str              # read | write | destructive | admin
    version: str                 # semver
    schema: dict                 # JSON Schema
    deprecated: bool = False
    deprecated_since: str | None = None
    replacement: str | None = None  # 指向新工具名

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    def register(self, name, server_id, capability, version, schema):
        # 冲突检测：同 server_id 同 capability 同 schema 名 → 报错
        if name in self._tools:
            existing = self._tools[name]
            if existing.server_id != server_id:
                raise ValueError(f"Tool {name} registered on {existing.server_id} and {server_id}")
        self._tools[name] = ToolEntry(name, server_id, capability, version, schema)

    def get_all_schemas(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.schema.get("description", ""),
                "inputSchema": t.schema,
                "meta": {"capability": t.capability, "version": t.version, "server": t.server_id},
            }
            for t in self._tools.values()
        ]

    def deprecate(self, name: str, replacement: str | None = None):
        e = self._tools[name]
        e.deprecated = True
        e.deprecated_since = datetime.now().isoformat()
        e.replacement = replacement

    def dump_snapshot(self, path: Path):
        """启动时 dump 注册表，CI 比对。"""
        path.write_text(json.dumps(
            [{"name": t.name, "server": t.server_id, "capability": t.capability,
              "version": t.version, "deprecated": t.deprecated} for t in self._tools.values()],
            indent=2, ensure_ascii=False,
        ))
```

### 4.6 Server 端通用框架

```python
# app/mcp_servers/_base.py
"""通用 MCP server 启动框架。"""
import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)


def build_server(name: str, tools: list[dict], handlers: dict, *, capability: str = "read", version: str = "1.0.0") -> Server:
    """注册 tools 到 MCP server。"""
    server = Server(name)
    for tool in tools:
        fn = tool["function"]
        server.register_tool(
            name=fn["name"],
            description=fn["description"],
            input_schema=fn["parameters"],
            handler=handlers[fn["name"]],
        )
    return server


async def run_server(name: str, tools: list[dict], handlers: dict, *, capability="read", version="1.0.0"):
    """启动 stdio MCP server。"""
    server = build_server(name, tools, handlers, capability=capability, version=version)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options(),
        )


def entrypoint(name, capability="read", version="1.0.0"):
    """装饰器：把函数变成 MCP server 入口。"""
    def decorator(func):
        async def main():
            tools, handlers = func()
            await run_server(name, tools, handlers, capability=capability, version=version)
        return main
    return decorator
```

**使用**（每个 server 一个文件）：

```python
# app/mcp_servers/builtin/candidate_server.py
from app.tools.candidate import tools, handlers
from app.mcp_servers._base import entrypoint


@entrypoint("mcp-candidate", capability="write", version="1.0.0")
def main():
    return tools, handlers


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 4.7 Skill 进程化

**改造 `app/skills/loader.py`**：每个 skill 启动一个独立 server 进程。

```python
# app/skills/loader.py
class SkillLoader:
    async def load(self, name: str | None = None) -> int:
        """discover SKILL.md → 启动独立 server 进程 → 注册到 MCPHost。"""
        skill_paths = await self.discover()
        for path in skill_paths:
            skill = await self.parse(path)
            if name and skill.name != name:
                continue
            # 生成临时 server 启动脚本
            server_script = self._generate_server_script(skill)
            # 启动 server
            params = StdioServerParameters(
                command="python",
                args=[str(server_script)],
            )
            server_id = f"skill-{skill.name}"
            await mcp_host._start_server({
                "id": server_id,
                "command": params.command,
                "args": params.args,
                "restart": "on-failure",
            })

    def _generate_server_script(self, skill: SkillDefinition) -> Path:
        """从 SKILL.md 生成临时 server 入口文件。"""
        template = f'''"""Auto-generated MCP server for skill: {skill.name}"""
import asyncio
import sys
sys.path.insert(0, "{Path(__file__).parent}")

from app.mcp_servers._base import entrypoint
from RestrictedPython import compile_restricted

HANDLER_CODE = """
{skill.handler_code}
"""

@entrypoint("{skill.name}", capability="{skill.capability}", version="{skill.version}")
def main():
    tools = {skill.tools_schema}
    handlers = {generate_restricted_handlers(skill.handler_code)}
    return tools, handlers

if __name__ == "__main__":
    asyncio.run(main())
'''
        path = Path(f"/tmp/skill_{skill.name}_server.py")
        path.write_text(template)
        return path
```

**沙箱**（真进程 + 资源限制）：

```python
# 在 supervisor.spawn 时加 preexec_fn
import resource

def _limit_resources():
    """子进程资源限制（Linux only，macOS 部分支持）。"""
    # CPU 时间：60s 软限、120s 硬限
    resource.setrlimit(resource.RLIMIT_CPU, (60, 120))
    # 内存：512MB
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    # 禁止 core dump
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # 文件大小：100MB
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))

# macOS 上 RLIMIT_AS / RLIMIT_CPU 行为不同，需要 fallback
```

---

## 5. 工程级升级（v2 → v3 保留并增强）

### 5.1 可观测性（OpenTelemetry 跨进程）

**问题**：tool call 跨 4 层（LLM → agent_service → MCPHost → subprocess），如何 trace？

**方案**：OTel context 序列化到 MCP JSON-RPC 头。

```python
# app/mcp/tracing.py
from opentelemetry import trace, propagate

class MCPTraicer:
    def span(self, name, attributes=None):
        """创建 span，把 context 注入到 carrier（dict）。"""
        tracer = trace.get_tracer("mcp")
        with tracer.start_as_current_span(name, attributes=attributes) as span:
            carrier = {}
            propagate.inject(carrier)  # 注入 traceparent / tracestate
            return _MCPContextSpan(span, carrier)

# subprocess 端：从 stdin 第一行读 trace context，恢复 parent span
def _read_trace_context(stdin_reader):
    # MCP 协议允许在 initialize 请求里带 _meta 字段
    # 我们扩展协议：第一个 initialize 请求带 trace context
    ...
```

**MCPHost 端每次 call_tool**：
- 创建 span，注入到 MCP JSON-RPC `_meta` 字段
- subprocess 端解析，link 到 parent span
- span attributes：`mcp.tool`, `mcp.server`, `mcp.call.duration`, `mcp.call.success`

**Prometheus 指标**（已有 `prometheus-client`，接上）：
```python
# app/mcp/metrics.py
from prometheus_client import Counter, Histogram, Gauge

mcp_calls_total = Counter(
    "mcp_calls_total",
    "Total MCP tool calls",
    ["tool", "server", "status"],  # status: success | error | timeout
)
mcp_call_duration = Histogram(
    "mcp_call_duration_seconds",
    "MCP tool call latency",
    ["tool", "server"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30],
)
mcp_server_up = Gauge(
    "mcp_server_up",
    "1 if server is up, 0 if down",
    ["server_id"],
)
mcp_server_restarts_total = Counter(
    "mcp_server_restarts_total",
    "Total server restarts",
    ["server_id"],
)
```

**Sentry**（已有 `sentry-sdk[fastapi]`）：
- MCPHost 启动失败 → Sentry 告警
- Server 重启次数超阈值 → Sentry 告警
- tool call 异常率 > 5% → Sentry 告警

### 5.2 真正的沙箱（进程级 + 资源限制）

**v3 的隔离就是真进程**，在 supervisor 拉起时加：

```python
# app/mcp/supervisor.py
async def _start(self, server_id, params, sandbox: SandboxPolicy):
    kwargs = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if sandbox.linux_only_limits:
        # Linux 才有 RLIMIT_*，macOS 部分支持
        kwargs["preexec_fn"] = _apply_resource_limits(sandbox)
    if sandbox.new_session:
        kwargs["start_new_session"] = True  # os.setsid()
    return await asyncio.create_subprocess_exec(params.command, *params.args, **kwargs)
```

**三层防护**：
1. **资源限制**（`resource.setrlimit`）：CPU、内存、文件大小、core dump
2. **新 session**（`os.setsid`）：防止 ctrl-c 传播、防止 kill 父进程连带
3. **AST 静态扫描**（仅对 skill）：RestrictedPython 编译

**未实现部分**（v3 不做，但留接口）：
- seccomp / AppArmor：需要 root 或容器化，v3 留 hook
- 网络策略（白名单域名）：v3.1 引入 `socket.gethostbyname` 黑名单
- chroot：v3.1 引入

### 5.3 工具 capability + RBAC

**tool metadata 声明**（在 `app/tools/<name>.py`）：

```python
# app/tools/candidate.py
from app.tools.metadata import tool_meta

@tool_meta(
    capability="write",  # read | write | destructive | admin
    requires_role="hr",  # hr | admin | recruiter
    rate_limit=100,      # 每用户每小时最多 100 次
    timeout=10,          # 默认 10s
    version="1.0.0",
)
def tools():
    return [...]
```

**policy.py 检查**：

```python
class MCPPolicy:
    def check_permission(self, user_id: str, tool_name: str) -> bool:
        entry = registry.get(tool_name)
        if entry.capability == "destructive":
            # 必须人工审批（已有 awaiting_approval 流程）
            return False  # 拒绝自动调用，必须走 orchestrator 审批
        user_role = self._get_user_role(user_id)
        if not self._role_allowed(user_role, entry.requires_role):
            return False
        return True
```

**危险操作分类**：
- `read`：get_*, list_*, search_* → 默认放行
- `write`：create_*, update_*, set_* → 默认放行，记 audit
- `destructive`：delete_*, archive_*, cancel_* → 强制走审批（已有 `awaiting_approval`）
- `admin`：install_skill, drop_cache → 仅 admin 角色

### 5.4 Schema 演进 + 向后兼容

**tool 声明版本**：
```python
@tool_meta(capability="read", version="1.0.0")
def create_candidate_v1():
    # 旧参数：name, email, phone
    ...
```

**版本共存**：
- `create_candidate_v1` (v1.0.0) + `create_candidate_v2` (v2.0.0) 同时注册
- LLM 看到的工具描述里 v1 标 `deprecated`，v2 标推荐
- 调 v1 → handler 内部 redirect 到 v2 + 警告

**deprecate 流程**：
```python
# 阶段 1：标 deprecated，handler 仍可用
registry.deprecate("create_candidate", replacement="create_candidate_v2")
# 阶段 2：3 个月后，host 加 deprecation_warning metric
# 阶段 3：6 个月后，handler 抛 RemovedError
```

**Schema 自动生成 OpenAPI**：
- MCPHost 启动时把注册表 dump 到 `app/mcp/_generated_tools_snapshot.json`
- `scripts/check_mcp_servers.py` 跑 `pydantic` 校验每个 tool 的 schema 合法
- CI fail：handler 不存在 / schema 无 description / 参数没 type

### 5.5 注册表 = 单一事实源 + CI 检查

**`scripts/check_mcp_servers.py`**（CI 跑）：

```python
# 1. 启动 host（dev 模式，单进程）
# 2. 抓 _generated_tools_snapshot.json
# 3. 对每个 tool：
#    - handler 函数存在
#    - handler 签名匹配 schema（必填参数都在）
#    - description 非空
#    - capability 在白名单
# 4. 对每个 server：
#    - 启动后 5s 内 list_tools 返回 ≥ 1
#    - call_tool 一个 smoke test 成功
```

**pre-commit hook**：
- 改 `app/tools/*.py` → 自动跑 `python -c "from app.tools.candidate import tools, handlers; assert len(handlers) > 0"`

---

## 6. 迁移路径（6 阶段，每阶段可独立发布）

### 阶段 0：MCP SDK 引入 + Server 框架（1 PR）
- `pip install "mcp[cli]>=1.0.0"`
- 新建 `app/mcp_servers/_base.py`（通用框架）
- 新建 `app/mcp_servers/builtin/utils_server.py` 作为**首个示范**（最简单的 4 个工具）
- `app/mcp_servers/config.json` 注册 utils server
- **退出标准**：
  - `python -m app.mcp_servers.builtin.utils_server` 启动后能 list_tools
  - `make test-mcp-utils` 用 mcp client 调通 `greet` / `get_current_time` / `calculate`
  - 现有 23 个其他工具路径**完全不动**（agent_service 仍走旧路径）

### 阶段 1：MCPHost 客户端 + Supervisor（2 PR）
- **PR-1a**：新建 `app/mcp/host.py` + `app/mcp/supervisor.py`（不接 agent_service，仅 standalone 测试）
- **PR-1b**：`app/mcp/registry.py` + `app/mcp/policy.py` + `app/mcp/tracing.py` + `app/mcp/metrics.py`（可观测性基础设施）
- 加 `GET /api/v1/mcp/tools` 端点暴露 utils server 的工具列表
- **退出标准**：
  - 启动 utils server 子进程，host 连上，list_tools 返回 4 个
  - 手动 kill utils server，supervisor 3s 内自动重启
  - 关闭 host，所有 server 子进程优雅退出
  - Prometheus `/metrics` 端点暴露 `mcp_calls_total` 等指标

### 阶段 2：内置 server 迁移（10 个 PR，每个 server 一个）
- 按依赖顺序逐个迁移到独立 server 进程：
  - PR-2.1 `mcp-utils`（**最简单，已在阶段 0 跑通**）
  - PR-2.2 `mcp-search`（1 个工具，依赖 httpx）
  - PR-2.3 `mcp-dashboard`（1 个工具，纯 DB）
  - PR-2.4 `mcp-knowledge`（2 个工具）
  - PR-2.5 `mcp-resume`（2 个工具，依赖文件）
  - PR-2.6 `mcp-application`（3 个工具）
  - PR-2.7 `mcp-evaluation`（4 个工具）
  - PR-2.8 `mcp-job`（5 个工具）
  - PR-2.9 `mcp-candidate`（8 个工具）
  - PR-2.10 `mcp-interview`（7 个工具，**最后因为最复杂**）
- 每个 PR 用**蓝绿切换**：新旧路径并行，新路径走 10% 流量 → 50% → 100%
- **退出标准**（每个 server）：
  - 旧路径所有 e2e 通过
  - 新 server 启动 + list_tools + call_tool smoke test 通过
  - 灰度 24h 无异常 → 切 100%
  - `app/tools/<name>.py` 改为纯函数（不再注册到 agent_service）

### 阶段 3：Skill 进程化（2 PR）
- **PR-3a**：实现 `app/mcp_servers/skills/_skill_runner.py`（从 SKILL.md 生成 server 入口）+ RestrictedPython 集成
- **PR-3b**：把 3 个 skill（weather / web_search / web-access）迁到独立进程
- **退出标准**：
  - `make skill-list` 看到 3 个 skill，每个跑独立 PID
  - weather skill 调用延迟增加 < 10ms（vs v2 进程内）
  - 任意一个 skill 挂了，主进程 + 其他 skill 正常

### 阶段 4：可观测性 + 权限 + Schema 演进（1 大 PR）
- 接入 OpenTelemetry（已在 `requirements.txt` 加 `mcp[cli]`，还需加 `opentelemetry-*`）
- Prometheus 指标全量上线
- Sentry 告警规则
- tool metadata 声明 cap + RBAC
- `_generated_tools_snapshot.json` 启动时 dump
- **`scripts/check_mcp_servers.py` + pre-commit**
- **退出标准**：
  - Jaeger UI 能看到 tool call 跨进程 trace
  - `curl /metrics` 看到所有指标
  - 改 `app/tools/candidate.py`，pre-commit 自动 fail
  - 用 hr 角色调 admin 工具 → 403

### 阶段 5：CI + 健康检查（1 PR）
- 改 `scripts/health-check.sh`：加 MCP server 健康检查步骤（7/7 pass）
- 加 `scripts/mcp-smoke-test.sh`：每个 server 跑 1 个工具调用验证
- 接入 GitHub Actions
- **退出标准**：
  - `bash scripts/health-check.sh` 7/7 pass
  - `bash scripts/mcp-smoke-test.sh` 13/13 server 通过
  - CI 上跑 `check_mcp_servers.py` exit 0

---

## 7. 兼容性 & 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| **13+ 进程冷启动慢（5-10s）** | 服务启动慢 | 阶段 4 加 lazy 启动（首次调用时拉起），supervisor 维护 warm pool |
| **stdio 通信延迟（1-5ms / call）** | 高频 tool call 场景性能下降 | 阶段 2 灰度监控；如 < 1000 QPS 不感知；高频 tool 可合并 |
| **stdio buffer 满（subprocess 死锁）** | subprocess 卡住 | 限制 `limit=1MB`、及时 drain；subprocess 内部不 print 大块日志 |
| **macOS 资源限制不全**（RLIMIT_AS 部分支持）| dev 环境限制不严 | 文档说明；生产用 Linux + 容器化 |
| **MCP SDK 版本兼容性** | 升级 SDK 破 13 个 server | 锁版本 `mcp==1.x.y`；升级时 13 个 server 一起回归 |
| **MCPHost 单点** | host 挂 = 全部 server 失效 | v1 接受；v3.1 引入 hot-standby host（Redis 协调）|
| **调试复杂** | dev 要看 13 个进程 | 加 `--single-process` 模式（v2 行为回退）；vscode launch.json 配 13 个 debug |
| **预存 `_BUILTIN_INSTALL_TOOLS` 依赖** | agent_service 还硬编码 5 个 install 工具 | 阶段 2 把 install 工具迁到 `mcp-installer` server |
| **seccomp / chroot 未实现** | 远程 SKILL.md 真能逃逸 | v3 不做真隔离，v3.1 引入；当前只靠 AST + RestrictedPython + RLIMIT_* |
| **OTel 跨进程 context 注入需要改 MCP 协议** | 可能不兼容第三方 MCP server | 用 MCP `_meta` 字段（spec 允许），向后兼容 |

---

## 8. 文件变更清单（汇总）

| 操作 | 文件 | 阶段 |
|------|------|------|
| 加依赖 | `requirements.txt`（`mcp[cli]>=1.0.0`, `opentelemetry-*`）| 0+4 |
| 新建 | `app/mcp_servers/_base.py` | 0 |
| 新建 | `app/mcp_servers/builtin/{utils,search,dashboard,...}_server.py` × 11 | 0+2 |
| 新建 | `app/mcp_servers/skills/{_skill_runner,weather,web_search,web_access}_server.py` | 3 |
| 新建 | `app/mcp_servers/config.json` | 0+2 |
| 新建 | `app/mcp/host.py` | 1a |
| 新建 | `app/mcp/supervisor.py` | 1a |
| 新建 | `app/mcp/registry.py` | 1b |
| 新建 | `app/mcp/policy.py` | 1b |
| 新建 | `app/mcp/tracing.py` | 4 |
| 新建 | `app/mcp/metrics.py` | 1b |
| 新建 | `app/mcp_servers/_generated_tools_snapshot.json`（自动生成）| 4 |
| 新建 | `app/api/mcp_tools.py` | 1a |
| 新建 | `app/core/observability.py` | 4 |
| 新建 | `scripts/check_mcp_servers.py` | 4 |
| 新建 | `scripts/mcp-smoke-test.sh` | 5 |
| 新建 | `tests/mcp/test_*.py` × 4 | 1+5 |
| 新建 | `tests/test_e2e_mcp.py` | 5 |
| 改 | `app/tools/__init__.py`（加 tool_meta 装饰器）| 0+4 |
| 改 | `app/tools/metadata.py`（加 capability 字段）| 0+4 |
| 改 | `app/tools/*.py` × 24（加 tool_meta）| 4 |
| 改 | `app/services/agent_service.py`（_get_tools/_get_handlers 调 MCPHost）| 1+2 |
| 改 | `app/skills/loader.py`（生成 skill server 进程）| 3 |
| 改 | `app/main.py`（lifespan 启动 MCPHost）| 1 |
| 改 | `docs/system-health-check.md`（加 MCP 检查）| 5 |
| 保留 | `app/mcp/bridge.py`（MCP ↔ OpenAI schema 转换，**复用**）| — |
| 保留 | `app/mcp/client.py`（远程 MCP HTTP 客户端）| — |
| 保留 | `app/mcp/manager.py`（远程 MCP 注册）| — |
| 保留 | `app/skills/base.py` / `gallery.py`（向后兼容）| — |

**总计**：~18 PR、~50 文件、~3500 行新代码 + ~500 行改动。

---

## 9. 退出标准（整个项目）

- [ ] `pip install mcp[cli]>=1.0.0` 装好，13 个 server 全部能 stdio 启动
- [ ] MCPHost 拉起所有 server 子进程 + 建立 stdio session + 索引工具
- [ ] supervisor：单个 server 挂了 3s 内自动重启，超 max_restarts 永久下线
- [ ] 任意 tool call 跨进程 P95 < 50ms（本地 dev）
- [ ] 远程 MCP（`/api/v1/mcp/servers`）仍能注册 + 调用，作为 RemoteSource 并入
- [ ] OTel trace 从 LLM → agent → MCPHost → subprocess → handler 全链路
- [ ] Prometheus `/metrics` 暴露 mcp_calls_total / mcp_call_duration / mcp_server_up
- [ ] Sentry 告警：server 重启超阈值 / call 异常率 > 5%
- [ ] tool metadata：capability + RBAC + rate limit 全量上线
- [ ] CI 跑 `check_mcp_servers.py` exit 0，pre-commit hook 装好
- [ ] `bash scripts/health-check.sh` 7/7 pass
- [ ] `bash scripts/mcp-smoke-test.sh` 13/13 server 通过
- [ ] 文档 `ai 招聘agent MCP服务器架构：...md` 与实现完全对齐
- [ ] dev 模式：单进程回退 (`--single-process` flag)
- [ ] macOS + Linux 都能跑（dev mac，prod Linux）

---

## 10. 未决问题（推荐答案）

| # | 问题 | 推荐答案 | 理由 |
|---|------|---------|------|
| 1 | 13 个进程冷启动 5-10s | 接受 + lazy 启动（首次调用拉起）| 启动慢是 trade-off，可观测性更重要 |
| 2 | stdio vs streamable-http | **stdio 主**（内置/skill），HTTP 备（远程）| 文档原意、零网络、零端口 |
| 3 | 进程数 vs 性能 | dev 接受 13 进程，prod 拆 pod | dev 单机足；prod k8s 自动扩缩 |
| 4 | 危险工具审批 | 复用现有 `awaiting_approval` 流程 | 不重复造轮 |
| 5 | MCPHost 单点 | v1 接受单点，v3.1 引入 standby | 先跑通再谈 HA |
| 6 | macOS 资源限制 | 接受部分失效，prod 走 Linux | dev 体验优先 |
| 7 | OTel context 注入 | 用 MCP `_meta` 字段（spec 允许）| 兼容第三方 |
| 8 | `--single-process` 模式 | **保留**（dev debug 友好）| 不用每次看 13 个进程 |
| 9 | Server 启动顺序 | 独立启动，无依赖 | 子进程各自加载自己需要的 |
| 10 | seccomp / chroot | v3 不做，v3.1 留 hook | v3 已是独立进程 + RLIMIT 足矣 |

---

## 11. 验证 SOP（每阶段必跑）

1. `make api:dev` 启动后 `ps aux | grep mcp_servers` 看到 N 个子进程
2. `curl -X POST /api/v1/auth/login` 拿 token
3. `curl -X GET /api/v1/mcp/tools -H "Authorization: Bearer $TOKEN"` 返回完整工具列表（MCP 格式 + OpenAI 格式都试）
4. `curl -X GET /api/v1/mcp/skills` 返回内置 + skill 列表
5. 手动 `kill -9` 一个 server 子进程 → 3s 内自动重启
6. `bash scripts/health-check.sh` → 7/7 pass
7. `bash scripts/mcp-smoke-test.sh` → 13/13 server 通过
8. Jaeger UI（如果有）看到 tool call 跨进程 trace
9. `curl /metrics | grep mcp_` 看到所有指标

---

## 12. Self-Review（v3 → 下一轮迭代候选）

### 12.1 v3 还有什么风险

| 风险 | 评估 | 缓解（v3.1）|
|------|------|------------|
| 进程数膨胀 | 13+ 是 hard cap | 允许合并：`mcp-utils + mcp-dashboard` 一个进程（共用 utils）|
| stdio 性能瓶颈 | 高 QPS 场景可能不够 | 引入 Unix domain socket（更快的 IPC）|
| MCP 协议升级 | SDK 锁版本，但 spec 演进 | 监控 MCP spec 变化，季度升级窗口 |
| 多语言 server | 暂未实现 | `_base.py` 留 Go/Rust adapter 接口 |
| 集群部署 | host 是单点 | v3.1 引入基于 Redis 的 host 协调 |

### 12.2 与文档的最终对齐

| 文档原话 | v3 实现 | 偏差 |
|---------|---------|------|
| "内置 MCP 工具（10 个 Server）"| ✅ 11 个（含 installer）| 加 1 个 installer（管理 skill）|
| "B 轨道：外部 Skill 加载"| ✅ 独立进程 | 无偏差 |
| "统一 MCP 协议层"| ✅ MCPHost 调度 | 无偏差 |
| "Skill 独立进程/容器"| ✅ 独立进程（v3.1 容器）| 容器化推迟到 v3.1 |
| "30s 超时"| ✅ supervisor RLIMIT_CPU + asyncio.wait_for | 资源限制 + 协议超时双保险 |
| "热更新"| ✅ reload server config 不重启 host | 无偏差 |

### 12.3 v3 评审结论

- ✅ **工程级**：13 进程 + supervisor + OTel + Prometheus + Sentry + RBAC + CI
- ✅ **长远**：版本演进 / 多语言 / 集群部署 / 容器化 全部留接口
- ✅ **可实施**：18 PR 拆解，每 PR ≤ 1-2 文件
- ✅ **可验证**：13 项退出标准，每项有具体跑法
- ⚠️ **代价**：启动慢 + 调试复杂 + macOS 限制不严 → 用 `--single-process` + lazy 启动 + Linux prod 缓解

---

## 13. v3 Self-Review（v4 增量修订）

> Sisyphus 代偿 momus 评审（OpenCode 余额不足）。**严格审视 v3 找深层漏洞**。

### 13.1 新发现 6 个深层漏洞

| # | 漏洞 | 严重度 | v3 漏点 |
|---|------|--------|--------|
| **V-1** | **启动风暴** — 13 个 server 冷启动 5-10s + 同时启动内存峰值 2.6GB | **关键** | 只说"lazy 启动"没具体策略；用户首次提问等 5s 体验崩 |
| **V-2** | **stdio buffer 死锁** — 简历解析返回 base64 > 1MB，server 内部 print 日志填满 pipe | **关键** | `limit=1MB` 没说明大 result 怎么走、server 端 print 怎么办 |
| **V-3** | **tool call 输入未验证** — LLM 传恶意参数（SQL 注入、命令注入），handler 信任 schema 但不验证 | **关键** | `call_tool(name, arguments)` 直接传 dict，缺 Pydantic 强校验 |
| **V-4** | **配置/密钥管理缺失** — 13 个 server 启动命令 + env 变量 + API key 在哪？dev/staging/prod 怎么分？ | 高 | 只提 `config.json`，没说非密/密分离、vault 注入 |
| **V-5** | **测试金字塔太薄** — 13 个 server 全测启动慢、e2e 启动 13 进程 mock 困难 | 高 | 只说 `tests/mcp/test_*.py`，没分 unit/integration/e2e 三层 |
| **V-6** | **文档同步缺失** — v3 实现完后那份 md 没列更新清单 | 中 | 12.2 节有"对齐表"但没"具体改什么" |

### 13.2 修复（按优先级）

#### V-1 修复：分批启动 + 预热 + 内存预算

```python
# app/mcp/supervisor.py — 启动策略
class StartupStrategy:
    """三阶段启动：core → secondary → lazy。"""

    CORE_SERVERS = {"mcp-candidate", "mcp-interview", "mcp-job", "mcp-utils"}
    # 第一批：用户高频调用，启动时并行拉起（4 个）

    SECONDARY_SERVERS = {"mcp-search", "mcp-dashboard", "mcp-knowledge", ...}
    # 第二批：启动后 30s 拉起（4 个）

    LAZY_SERVERS = {"mcp-installer", "skill-*"}
    # 第三批：首次调用才拉起

    async def start_all(self, host, config):
        # 1. core batch: 并行拉起，等所有 list_tools 返回
        await self._start_batch(host, config, self.CORE_SERVERS, parallel=True, timeout=30)

        # 2. secondary batch: 启动 30s 后拉起（不阻塞启动）
        asyncio.create_task(self._delayed_start(host, config, self.SECONDARY_SERVERS, delay=30))

        # 3. lazy: 注册到 registry 但不启动，首次 call_tool 时拉起
        for srv in self.LAZY_SERVERS:
            host.registry.register_pending(srv, config[srv])

        # 4. 内存预算监控：每 10s 检查总 RSS，超 4GB 触发告警
        asyncio.create_task(self._memory_watchdog(threshold_gb=4.0))
```

#### V-2 修复：stdio buffer 策略

```python
# app/mcp/supervisor.py — 启动参数
async def _start(self, server_id, params):
    return await asyncio.create_subprocess_exec(
        params.command, *params.args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        # stderr 重定向到日志文件，不用 pipe（避免死锁）
        stderr=open(f"logs/mcp_{server_id}.log", "ab"),
        # stdout buffer 提升到 8MB（简历 base64 等大 result）
        limit=8 * 1024 * 1024,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},  # 关键：server 端不缓冲
    )

# 大 result 走文件：handler 返回 {"_type": "file_ref", "path": "/tmp/abc"}
# MCPHost 读到后从文件读 + 删文件
class LargeResultHandler:
    THRESHOLD = 1 * 1024 * 1024  # 1MB

    def maybe_to_file(self, result: dict) -> dict:
        serialized = json.dumps(result, ensure_ascii=False)
        if len(serialized) > self.THRESHOLD:
            path = f"/tmp/mcp_large_{uuid4().hex}.json"
            Path(path).write_text(serialized)
            return {"_type": "file_ref", "path": path, "size": len(serialized)}
        return result
```

#### V-3 修复：tool call 输入 Pydantic 强校验

```python
# app/mcp/host.py — call_tool 加验证
from pydantic import ValidationError

class MCPHost:
    async def call_tool(self, tool_name, arguments, *, user_id=None):
        entry = self.registry.get(tool_name)
        if not entry:
            raise ToolNotFound(tool_name)

        # 1. Pydantic 校验（schema 必须含 input model class）
        if entry.input_model:
            try:
                arguments = entry.input_model.model_validate(arguments)
            except ValidationError as e:
                raise InvalidArguments(tool_name, e.errors())

        # 2. SQL/命令注入兜底：handler 必须用 SQLAlchemy / 参数化
        # （写在 RBAC policy 里强制）

        # 3. 限流
        await self.policy.acquire(user_id, tool_name)

        # 4. 调用
        with self.tracer.span(f"mcp.call.{tool_name}"):
            ...
```

**tool 模块声明 input_model**：

```python
# app/tools/candidate.py — 改造
from pydantic import BaseModel, EmailStr
from app.tools.metadata import tool_meta

class CreateCandidateInput(BaseModel):
    name: str | None = None
    email: EmailStr
    phone: str | None = None
    # ...

@tool_meta(capability="write", input_model=CreateCandidateInput)
def tools():
    return [...]  # schema 从 CreateCandidateInput 自动生成
```

#### V-4 修复：分层配置 + 密钥注入

```python
# app/mcp/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class ServerConfig(BaseModel):
    id: str
    command: str
    args: list[str]
    env_keys: list[str] = []  # 需要从 vault 注入的密钥名
    restart: str = "on-failure"
    max_restarts: int = 5
    timeout: int = 30

class MCPConfig(BaseSettings):
    servers: list[ServerConfig]
    # 从 .env / 环境变量 / vault 读

    model_config = {"env_file": ".env", "extra": "ignore"}

def load_config(path: Path = Path("app/mcp_servers/config.json")) -> MCPConfig:
    """加载配置 + 注入密钥到 env。"""
    raw = json.loads(path.read_text())
    cfg = MCPConfig.model_validate(raw)
    for srv in cfg.servers:
        for key in srv.env_keys:
            # 从 vault / .env 读（优先级：vault > env > .env）
            value = os.getenv(key) or _read_from_vault(key)
            if not value:
                raise ConfigError(f"Missing env: {key} for server {srv.id}")
            srv.env[key] = value
    return cfg
```

**config.json 例子**（非密）：
```json
{
  "servers": [
    {
      "id": "mcp-search",
      "command": "python",
      "args": ["-m", "app.mcp_servers.builtin.search_server"],
      "env_keys": ["TAVILY_API_KEY"],
      "timeout": 15
    }
  ]
}
```

**`.env`**（密，不入库）：
```
TAVILY_API_KEY=tvly-xxx
QWEATHER_API_KEY=xxx
```

#### V-5 修复：测试金字塔三层

```python
# tests/mcp/ — 三层结构
tests/mcp/
├── unit/                          # 不启动 subprocess，纯逻辑测试
│   ├── test_supervisor_logic.py   # RestartPolicy / 退避计算
│   ├── test_registry.py           # 冲突检测 / deprecate
│   ├── test_policy.py             # RBAC / rate limit
│   ├── test_large_result.py       # V-2 大 result 文件化
│   └── test_config.py             # 配置加载 / vault 注入
├── integration/                   # 启动 1-2 个真 server，stdio 通信
│   ├── test_utils_server.py       # mcp-utils 完整 list + call
│   ├── test_skill_runner.py       # SKILL.md → server 启动
│   └── test_supervisor_restart.py # kill server → 验证重启
└── e2e/                           # 启动 13 个真 server，host 端到端
    ├── conftest.py                # 共享 fixture：启动 host + 13 server
    ├── test_full_tool_catalog.py  # 验证所有 tool 可 call
    └── test_routing.py            # LLM 模拟 → 验证路由正确

# CI 配置：
# - unit: 每次 push 跑（< 30s）
# - integration: 每次 PR 跑（1-2 min）
# - e2e: 每日 / release 前跑（5-10 min，启动 13 进程慢）
```

**mock 策略**（e2e 不能每次跑）：

```python
# tests/mcp/conftest.py
@pytest.fixture
def mock_mcp_host(monkeypatch):
    """单进程 fake host，跳过 subprocess。"""
    from app.mcp.fake_host import FakeMCPHost
    return FakeMCPHost(tools={...}, handlers={...})

# app/mcp/fake_host.py — 新增
class FakeMCPHost:
    """不启动 subprocess，直接调 handlers。用于测试。"""
    def __init__(self, tools, handlers):
        self.registry = {t["name"]: ToolEntry(...) for t in tools}
        self.handlers = handlers

    async def call_tool(self, name, arguments):
        handler = self.handlers[name]
        result = handler(**arguments)
        if asyncio.iscoroutine(result):
            result = await result
        return result
```

#### V-6 修复：文档同步清单

```markdown
## 文档同步清单（v3 实施完成后必做）

| 文档 | 改什么 |
|------|--------|
| `ai 招聘agent MCP服务器架构：...md` | 加 v3 实施注（"实际用 mcp Python SDK + stdio，supervisor 管理 13 进程"）|
| `README.md` | Quick Start 加 "13 个 MCP server 子进程" 说明 |
| `docs/system-health-check.md` | 加 MCP server 7 步检查 |
| `docs/architecture-diagrams.md` | 重画架构图（v3 三轨道进程图）|
| `app/mcp_servers/config.json` | 加注释说明每字段含义 |
| `Makefile` | 加 `make mcp-list / mcp-restart / mcp-logs` |
| `.env.example` | 加 TAVILY_API_KEY / QWEATHER_API_KEY / 等 |
```

### 13.3 v4 增量修改清单

| 操作 | 文件 | 阶段 |
|------|------|------|
| 改 | `app/mcp/supervisor.py`（V-1 启动策略 + V-2 stderr 重定向）| 1a |
| 改 | `app/mcp/host.py`（V-3 Pydantic 校验 + V-2 大 result）| 1b |
| 新建 | `app/mcp/large_result.py`（V-2 file ref）| 1b |
| 新建 | `app/mcp/config.py`（V-4 分层配置）| 1b |
| 新建 | `app/mcp/fake_host.py`（V-5 测试用）| 1b |
| 改 | `app/tools/metadata.py`（V-3 加 input_model 字段）| 0+4 |
| 改 | `app/tools/*.py` × 24（V-3 加 Pydantic InputModel）| 4 |
| 改 | `app/mcp_servers/config.json`（V-4 加 env_keys）| 0+2 |
| 改 | `tests/mcp/`（V-5 三层结构）| 1+5 |
| 改 | 6 个文档（V-6 同步清单）| 5 |

**新增工作量**：~600 行新代码 + ~200 行改 + 6 个文档同步。**总投资**：~4000 行。

### 13.4 v4 退出标准（新增 5 项）

- [ ] **V-1**：13 server 冷启动 < 3s（core batch 并行）、< 8s（全量）
- [ ] **V-2**：5MB tool result 走 file ref，subprocess 不死锁
- [ ] **V-3**：tool 100% 声明 Pydantic InputModel，CI 校验 schema 一致
- [ ] **V-4**：dev/staging/prod 三套 config 隔离，密钥不入库
- [ ] **V-5**：unit < 30s / integration < 2min / e2e < 10min 三层独立
- [ ] **V-6**：6 个文档同步完成，`grep "13 个 server"` 都能搜到

### 13.5 v4 评审结论

- ✅ **解决了 v3 的 6 个深层漏洞**（启动 / 死锁 / 安全 / 配置 / 测试 / 文档）
- ✅ **工程级更深一层**：Pydantic 校验 / 大 result 文件化 / 密钥注入 / 三层测试
- ✅ **长远可扩展**：FakeMCPHost 支撑单测 / config layer 支撑多环境 / 启动策略支撑水平扩缩
- ⚠️ **新增 600 行代码 + 6 个文档同步**，但都是"一次性投资"，后续 v5+ 不用再补
- **下一步**：开 PR-0（装 SDK + utils_server + V-2/V-3/V-4 的最小骨架）

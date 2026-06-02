# Agent 提示词补充方案 — v2 提案（Momus-reviewed）

> **依据文档**：`AI招聘Agent_完整提示词实现方案.md`（Hermes-style 6 层架构）
> **当前状态**：2026-06-02 扫描结果
> **修订记录**：v1 → v2（修复 v1 中 12 个 Momus 标记的问题，见文末 §十三）
> **目的**：在不动现有 9 个 Specialist Prompt 内容的前提下，**新增 3 层**（SOUL/MEMORY/USER）+ **补全 7 个 Skills（工具化加载）** + **升级 PromptLoader**

---

## 一、当前实现盘点

### 1.1 已有 Prompt 资产（10 个 .md）

| 文件 | 行数 | 用途 |
|---|---:|---|
| `prompts/system.md` | 36 | 多 Agent 系统对外身份 |
| `prompts/orchestrator.md` | 82 | Orchestrator Agent |
| `prompts/router.md` | 48 | Router Agent |
| `prompts/resumeParser.md` | 38 | 简历解析 Agent |
| `prompts/sourcing.md` | 114 | 寻源 Agent |
| `prompts/screening.md` | 108 | 筛选 Agent |
| `prompts/interview.md` | 96 | 面试 Agent |
| `prompts/offering.md` | 85 | Offer Agent |
| `prompts/onboarding.md` | 99 | 入职 Agent |
| `prompts/analytics.md` | 83 | 数据 Agent |
| **小计** | **789** | — |

**Loader 现状** (`prompts/__init__.py`)：单文件加载，文件名→字符串，内存 dict 缓存。

### 1.2 缺失资产（与方案对比）

| 方案要求 | 当前状态 | v2 目标 |
|---|---|---|
| `SOUL.md` | ❌ | ✅ 新增 |
| `MEMORY.md` | ❌ | ✅ 新增 |
| `USER.md`（per user）| ❌ | ✅ 新增（文件系统） |
| `skills/*.md`（工具化加载）| ❌ | ✅ 新增（**7 个 skill 文件**） |
| `safety_rules.md`（独立）| ❌ | ✅ 新增（v1 **不抽取** 9 Agent 内容） |
| 分层 `PromptBuilder` | ❌ | ✅ 新增 `prompt_builder.py` |
| `PromptCacheManager`（带失效）| ⚠️ 弱 | ✅ 新增 `cache_manager.py` |
| `load_skill()` 工具（LLM 主动调用）| ❌ | ✅ 新增 + 注册到 LLM tool schema |
| Ephemeral 临时层 | ❌ | ✅ 新增 `ephemeral.py` |

---

## 二、9 大缺口 + 9 个补丁

### 缺口 1：跨 Agent 共享"灵魂"

**问题**：9 个 Specialist 各自定义角色 + 安全约束 + 语气 → 改一次要改 10 个文件。

**方案**：`prompts/SOUL.md`（~100 行，admin hardcode，git 版本管理）

**接入点**：`app/agents/base.py::build_system_prompt()` 第 1 段

### 缺口 2：组织记忆

**问题**：无公司招聘规范、薪酬带宽、渠道优先级 → 每次会话从零开始。

**方案**：`prompts/MEMORY.md`（~120 行，admin hardcode）

**接入点**：`PromptBuilder` 第 2 段

### 缺口 3：用户画像（per user）

**问题**：HR 偏好（输出格式、关注指标、沟通语言）无持久化。

**方案**：
- `prompts/USER.md`（默认模板，~60 行）
- `settings/users/{user_id}/memory.md`（per user 副本，v1 用文件系统）
- API：`GET/PUT /api/v1/users/me/memory`
- 权限：**仅本人可读写**；admin 可看不可改
- 审计：写操作记 `audit_logs` 表

**接入点**：`PromptBuilder` 第 3 段，`load_user_memory(user_id)`

### 缺口 4：Skills 层（领域知识外置）

**问题**：9 Agent Prompt 硬编码了 BEI 问题库、4 维评估框架、渠道策略 → 重复、非工程师改不动。

**方案**：`prompts/skills/` 7 个 .md 文件

| Skill | 工具名 |
|---|---|
| `skills/resume_parser.md` | `load_skill(name="resume_parser")` |
| `skills/screening_framework.md` | `load_skill(name="screening_framework")` |
| `skills/interview_questions.md` | `load_skill(name="interview_questions")` |
| `skills/sourcing_channels.md` | `load_skill(name="sourcing_channels")` |
| `skills/offer_negotiation.md` | `load_skill(name="offer_negotiation")` |
| `skills/onboarding_workflow.md` | `load_skill(name="onboarding_workflow")` |
| `skills/recruitment_analytics.md` | `load_skill(name="recruitment_analytics")` |

**关键设计**：v1 **不抽取** 9 Agent 内容（避免动 9 个文件）。skills 独立成文，**与现有 Agent Prompt 并存**。后续 v2 再做内容合并。

**接入点**：注册为 LLM tool（OpenAI / Anthropic function calling），LLM 按需调用。

### 缺口 5：安全规则集中化

**问题**：安全规则（数据脱敏、权限、一票否决）散落在 9 Agent。

**方案**：`prompts/safety_rules.md`（~60 行，admin hardcode）

v1 **只新增不抽取**：SOUL.md 末尾引用 `safety_rules.md`，Agent Prompt 暂不引用（保持纯增量）。

### 缺口 6：分层 PromptBuilder

**方案**：`prompts/prompt_builder.py`（~180 行，详见 §四）

### 缺口 7：版本化缓存

**方案**：`prompts/cache_manager.py`（~120 行，详见 §五）

### 缺口 8：Ephemeral 临时层

**问题**：调试 / A-B 测试时需要临时覆盖 Prompt，但当前没机制。

**方案**：`prompts/ephemeral.py`（~50 行）
- `ephemeral_override(text)` 函数
- 优先级最高，不缓存
- 仅 dev / staging 启用（`EPHEMERAL_ENABLED=true`）
- 生产默认禁用

### 缺口 9：USER 持久化基础设施

**问题**：USER.md 模板可放仓内，但 per user 副本不能。

**方案**：
- 仓内：`prompts/USER.md` 模板
- 仓外：`settings/users/{user_id}/memory.md`（`.gitignore` 排除）
- 默认从模板复制：`shutil.copy(template, user_path)`
- 路径配置：`settings_dir = Path(os.getenv("SETTINGS_DIR", "./.runtime/users"))`

---

## 三、新增文件清单

```
apps/api/app/agents/prompts/
├── SOUL.md                                  ← 新增（~100 行）
├── MEMORY.md                                ← 新增（~120 行）
├── USER.md                                  ← 新增（~60 行模板）
├── safety_rules.md                          ← 新增（~60 行）
├── skills/                                  ← 新增目录
│   ├── resume_parser.md                     ← 新增
│   ├── screening_framework.md               ← 新增
│   ├── interview_questions.md               ← 新增
│   ├── sourcing_channels.md                 ← 新增
│   ├── offer_negotiation.md                 ← 新增
│   ├── onboarding_workflow.md               ← 新增
│   └── recruitment_analytics.md             ← 新增
├── prompt_builder.py                        ← 新增（~180 行）
├── cache_manager.py                         ← 新增（~120 行）
├── ephemeral.py                             ← 新增（~50 行）
├── tool_registry.py                         ← 新增（~80 行，注册 load_skill 到 LLM）
└── __init__.py                              ← 扩展（新增 build_layered_prompt 等）

runtime/
└── users/                                   ← 新增（.gitignore）
    └── {user_id}/memory.md                  ← 运行时生成
```

**总计**：4 个新 Prompt 文件 + 7 个 skills + 4 个新模块 + 1 个仓外 runtime/ 目录 = **16 个新组件**。

**不动**：9 个现有 Agent Prompt，base.py 仅新增 1 行调用（向后兼容）。

---

## 四、PromptBuilder 6 层组装

```python
# prompt_builder.py
from dataclasses import dataclass

@dataclass
class PromptBundle:
    soul: str           # Layer 1: 稳定（admin hardcode）
    memory: str         # Layer 2: 组织（admin hardcode）
    user: str           # Layer 3: 用户（per user，文件系统）
    project: str        # Layer 4: 项目（AGENTS.md 预留，v1 留空）
    skills_index: str   # Layer 5: 技能索引（v1 留空，工具化后不注入）
    agent: str          # Layer 6: Agent 专层（screening.md / interview.md / ...）
    safety: str         # Layer 7: 安全（每次强制注入）
    env: str            # Layer 8: 环境（时间/租户/语言）
    ephemeral: str = "" # Layer 9: 临时（不缓存，最高优先级）


def build_layered_prompt(
    user_id: str,
    active_agent: str,
    context: dict,
    ephemeral: str | None = None,
) -> PromptBundle:
    """Hermes-style 6 层组装。"""
    return PromptBundle(
        soul=load_soul(),
        memory=load_memory(),
        user=load_user_memory(user_id),
        project=load_project_agents_md(),  # v1 返回 ""
        skills_index=build_skills_index(),  # v1 返回 ""（工具化后不注入）
        agent=load_prompt(active_agent),   # 兼容现有 loader
        safety=load_safety_rules(),
        env=build_environment_hints(context),
        ephemeral=ephemeral or "",
    )


def assemble(bundle: PromptBundle) -> str:
    parts = [bundle.soul, bundle.memory, bundle.user, bundle.project,
             bundle.agent, bundle.safety, bundle.env, bundle.ephemeral]
    return "\n\n---\n\n".join(p for p in parts if p)
```

**关键设计**：
- `skills_index` **不进入默认 system prompt**（决策 #3 = 工具化）
- LLM 通过 `load_skill` 工具按需拉取 skills 内容
- `assemble()` 用 `---` 分隔段落

---

## 五、CacheManager + 边界处理

```python
# cache_manager.py
import threading
from pathlib import Path
from dataclasses import dataclass

@dataclass
class CacheEntry:
    content: str
    mtime: float
    size: int
    version: int

class PromptCacheManager:
    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._version = 0

    def get(self, key: str, path: Path) -> str:
        """带 mtime 失效的读取。文件不存在返回空串 + warning log。"""
        with self._lock:
            entry = self._cache.get(key)
            try:
                stat = path.stat()
                if entry and entry.mtime == stat.st_mtime and entry.size == stat.st_size:
                    return entry.content
                content = path.read_text(encoding="utf-8")
                self._cache[key] = CacheEntry(content, stat.st_mtime, stat.st_size, self._version)
                return content
            except FileNotFoundError:
                return ""  # 边界：文件不存在不抛

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._cache.clear()
                self._version += 1
            else:
                self._cache.pop(key, None)
                self._version += 1


_cache = PromptCacheManager()


def cached_read(key: str, path: Path) -> str:
    return _cache.get(key, path)
```

**边界**：
- 文件不存在 → 返回空串（不抛）
- 文件编码错误 → 抛 `UnicodeDecodeError`（让上层捕获）
- 并发：`threading.Lock` 保护
- 失效：mtime + size 同时变化才重新读

---

## 六、实施路线（3 Phase × 1 周 = 3 周）

### Phase 依赖图

```
Phase 1（基础）──┬─→ Phase 2（Skills 工具化）
                └─→ Phase 3（USER 持久化）

Phase 2 和 Phase 3 可并行。
任一 Phase 可独立关闭（env flag）。
```

### Phase 1：基础（W1，5 天）

| Day | 任务 | 验收 | 测试 |
|---|---|---|---|
| 1 | 写 `SOUL.md` + `MEMORY.md` + `USER.md` + `safety_rules.md` | 4 文件存在 + 行数符合 §三 + 内容 review checklist 通过 | 4 文件 content hash 锁定（防漂移） |
| 2 | 写 `prompt_builder.py` + `cache_manager.py` | dataclass + 9 字段 + `assemble()` + cache mtime 失效通过 | `test_prompt_builder.py` (8 用例) + `test_cache_manager.py` (6 用例) |
| 3 | 扩展 `prompts/__init__.py` 新增 `build_layered_prompt()` / `load_soul()` / `load_memory()` / `load_safety_rules()` / `load_user_memory()` | 旧 `load_prompt()` 仍工作（向后兼容）| `test_init_compat.py` (3 用例) |
| 4 | 接入 `base.py::build_system_prompt()`，env flag `ENABLE_LAYERED_PROMPT=false` 时退回旧实现 | 现有 2,014 测试**全过** | 跑全套 |
| 5 | 集成测试：end-to-end 构造 user_id + active_agent，组装后断言 8 段都在 / 顺序正确 / `---` 分隔 | e2e 组装正确 | `test_prompt_integration.py` (4 用例) |

**Phase 1 总测试** = 2,014 + 21 = **2,035 passed**

**Phase 1 验收门**（必须全过才进 P2）：
- [ ] 现有 2,014 测试零回归
- [ ] 新增 21 测试全过
- [ ] `ENABLE_LAYERED_PROMPT=false` 时行为字节级等价于 P1 前
- [ ] `pytest --cov=app/agents/prompts` ≥ 95%
- [ ] `SOUL.md` / `MEMORY.md` / `safety_rules.md` 经 1 人 review 通过

### Phase 2：Skills 工具化（W2，5 天，可与 P3 并行）

| Day | 任务 | 验收 | 测试 |
|---|---|---|---|
| 1 | 写 7 个 `skills/*.md`（独立成文，与 9 Agent 内容**不重复**）| 7 文件存在 + 工具名映射表 + 1 人 review | 7 文件 content hash 锁定 |
| 2 | 写 `tool_registry.py`，注册 `load_skill(name)` 到 LLM function calling schema | OpenAI / Anthropic 工具定义 JSON 正确 | `test_tool_registry.py` (5 用例) |
| 3 | 接入 `base.py`：`LLM_AVAILABLE_TOOLS` 包含 `load_skill` | LLM 实际调用能拿到 skill 内容 | `test_skill_integration.py` (4 用例) |
| 4 | 灰度：`SKILLS_ENABLED=false` 时不注册工具 | env flag 工作 | 现有测试 + 1 env test |
| 5 | 文档：`docs/skills-authoring.md`（如何写 skill） | 1 个示例 skill 通过文档流程 | — |

**Phase 2 总测试** = 2,035 + 9 = **2,044 passed**

**Phase 2 验收门**：
- [ ] P1 测试零回归
- [ ] 新增 9 测试全过
- [ ] `load_skill("non_existent")` 返回明确错误，不静默
- [ ] 7 个 skill 工具调用实际能加载内容（手动跑一次）

### Phase 3：USER 持久化（W3，5 天，可与 P2 并行）

| Day | 任务 | 验收 | 测试 |
|---|---|---|---|
| 1 | 仓内 `USER.md` 模板 + `runtime/users/{user_id}/` 目录 + 首次访问自动 copy | 模板存在 + 目录在 .gitignore + 自动 copy 逻辑 | `test_user_memory_fs.py` (6 用例) |
| 2 | API：`GET /api/v1/users/me/memory` + `PUT /api/v1/users/me/memory` | 权限：仅本人；admin 只读；写操作入 audit log | `test_user_memory_api.py` (8 用例) |
| 3 | 接入 `PromptBuilder.load_user_memory(user_id)`，env flag `USER_MEMORY_ENABLED=false` 退回默认 USER.md | env flag 工作 + 现有用户不受影响 | 现有 + 2 env test |
| 4 | USER 注入到 SOUL/MEMORY/AGENT 之后 | e2e 组装含 user 段 | `test_user_integration.py` (2 用例) |
| 5 | 文档：`docs/user-memory.md` | 1 个 user 端到端通过 | — |

**Phase 3 总测试** = 2,035 + 18 = **2,053 passed**（P2 与 P3 并行时同时为 2,053）

**Phase 3 验收门**：
- [ ] P1 测试零回归
- [ ] 新增 18 测试全过
- [ ] USER 写操作有 audit log 记录
- [ ] admin 越权改 USER 返回 403

### v1.5（拆出，**不在 v1 范围**）

- USER 编辑 UI（前端 SPA 工作）
- 9 Agent Prompt 内容抽到 skills（refactor）
- MEMORY 内容自动归纳（analysis agent）
- Skill 版本管理（curator）

---

## 七、预期效果（如实版）

| 指标 | P1 前 | P1 后 | P2 后 | P3 后 |
|---|---|---|---|---|
| 共享身份维护成本 | 9 份 | 1 份 SOUL | 1 份 | 1 份 |
| system prompt 长度（默认） | ~3K tokens | ~4.2K（+40%）| ~4.2K（不加载 skill）| ~4.5K（+user）|
| system prompt 长度（用 skill）| — | — | ~5K（按需 1 个 skill）| ~5.3K |
| **节省** | — | **负** | **节省靠 LLM 选择不加载** | 同 P2 |
| 招聘领域知识可编辑性 | 改 .py 部署 | 改 .md 部署 | 改 .md 部署 | 同 |
| per-user 个性化 | ❌ | ❌ | ❌ | ✅ |
| 覆盖率 | 90.43% | ~91% | ~91.5% | ~92% |

**诚实结论**：v1 在 context 长度上是**净增加**，不是节省。节省要等 P2 工具化被 LLM 充分利用 + P3 per-user 缓存命中率提升后才显现。**不能把"30-50% 节省"当 v1 卖点**。

---

## 八、决策点（全部已定）

| # | 决策 | 采用 | 理由 |
|---|---|---|---|
| 1 | SOUL 编辑权 | **A. admin hardcode** | 用户已选；v1 简单可控 |
| 2 | USER.md 存储 | **A. 文件系统** | 简单、git diff 友好、零依赖；v2 迁 DB |
| 3 | Skills 加载 | **B. LLM 工具调用** | 用户已选；省 LLM 主动决定 |
| 4 | safety_rules 拆分 | **拆** | 独立文件便于审阅；v1 不抽 9 Agent 内容（纯增量） |
| 5 | MEMORY 内容来源 | **A. HR 手填**（v1）| v1 简单可控；v2 引入 analysis 自动归纳 |
| 6 | Mermaid 图表 Prompt | **加** | 已有 architecture-diagrams.md 先例 |
| 7 | Phase 1 Day 3 抽 safety | **跳过 v1** | 保持纯增量；v2 单独 refactor phase |
| 8 | Phase 3 UI | **拆 v1.5** | v1 只做存储 + API；前端工作量大 |
| 9 | 上下文成本预期 | **如实** | v1 是增加不是节省，靠 P2 工具化才省 |

---

## 九、回滚策略（每个 Phase 独立可关）

```bash
# Phase 1 关闭
export ENABLE_LAYERED_PROMPT=false  # 退回 load_prompt(name) 单文件

# Phase 2 关闭
export SKILLS_ENABLED=false  # 不注册 load_skill 工具

# Phase 3 关闭
export USER_MEMORY_ENABLED=false  # 用 USER.md 模板，不用 per-user 文件
```

**回滚测试**（P1 验收必跑）：
- `ENABLE_LAYERED_PROMPT=false` + 旧测试全过 = 字节级等价
- `SKILLS_ENABLED=false` + 旧测试全过 = 不影响现有 Agent 行为
- `USER_MEMORY_ENABLED=false` + 旧测试全过 = 所有用户走默认模板

---

## 十、v1 不做

- ❌ Self-Evolution（自动优化 Prompt）— v3
- ❌ 9 Agent 内容抽到 skills（refactor）— v2 独立 phase
- ❌ MEMORY 自动归纳 — v2
- ❌ Skill 版本管理（curator）— v2
- ❌ Context compressor（摘要压缩）— v2
- ❌ USER 编辑 UI — v1.5
- ❌ Mermaid 自动生成（运行时）— v2

---

## 十一、关键文件预览

### SOUL.md（v1 草稿，~100 行）

```markdown
# SOUL.md — AI 招聘系统核心身份（所有 Agent 共享）

## 身份
你是 **RecruitAgent**，多 Agent 协作驱动的 AI 招聘助手。

## 核心能力
寻源 / 简历解析 / 筛选 / 面试 / Offer / 入职 / 数据分析

## 行为准则
- **专业**：HR 专业术语，结构化输出
- **客观**：评估基于事实，避免年龄/性别/地域偏见
- **保密**：候选人脱敏（手机 138****8888）
- **诚实**：不确定时明确告知
- **可追溯**：每条建议附依据

## 安全底线（每次强制）
1. 禁止生成歧视性内容
2. 评价区分"事实"与"推断"
3. 发送 offer / 拒绝信 / 删除候选人 → human-loop 审批
4. 跨境 / 薪酬 / 身份证号 → L3 + 脱敏
5. 触发"我不知道"必须显式声明

## 语气
- 对 HR：专业 + 简洁 + bullet/表格
- 对系统调用：精确 + 严谨
- 中文为主，技术术语保留英文
```

### MEMORY.md（v1 草稿，~120 行）

含 5 段：面试轮次标准 / 反馈时效 / 一票否决 / 渠道优先级（按岗位类型） / 薪酬带宽（2026 Q2） / 已验证有效策略（JD 优化、面试前清单、48h offer 等）

### USER.md（v1 草稿，~60 行）

含 5 段：基本信息 / 偏好（输出格式、量化要求、决策风格） / 关注指标（试用期通过率、留存率、漏斗、ROI） / 学习模式

### safety_rules.md（v1 草稿，~60 行）

从 9 Agent 抽出**不重复**的安全规则（脱敏规则、权限矩阵、合规清单），v1 **不修改** 9 Agent Prompt，仅 SOUL.md 末尾引用。

### prompt_builder.py（详见 §四）+ cache_manager.py（详见 §五）

---

## 十二、立即可做的事

1. **用户确认本文档**（v2 修订版，约 10 分钟阅读）
2. **指派实施**：建议
   - dev agent：写 SOUL/MEMORY/USER/safety/skills 11 个新文件
   - Sisyphus：写 prompt_builder.py / cache_manager.py / ephemeral.py / tool_registry.py
   - Sisyphus：写所有 48 个新测试
   - Sisyphus：跑全套 + 修回归
3. **启动 Phase 1**

---

## 十三、v1 → v2 修订记录

| # | v1 问题 | v2 修复 |
|---|---|---|
| 1 | P1 Day 3 抽 safety vs "纯增量" 矛盾 | P1 跳过抽取，v2 再做 |
| 2 | P2 工具化 vs 索引注入矛盾 | 工具化下不注入索引 |
| 3 | P3 UI 范围爆炸 | 拆 v1.5，v1 只做 API |
| 4 | §三 8 组件 vs §九 "4 文件回滚" 不一致 | 统一为 16 组件，每个有明确回滚 env |
| 5 | "30-50% 节省" 不成立 | 如实写"v1 是增加，节省靠 P2 工具化" |
| 6 | 决策 #4 #5 #6 未让用户定 | 全部已决（v2 §八） |
| 7 | USER 存储未给推荐 | 推荐 A 文件系统 |
| 8 | 缺集成测试 | 4 个 e2e 组装测试 |
| 9 | 缺可验证 KPI | P1/P2/P3 验收门（21+9+18 测试 + env 行为字节级等价） |
| 10 | 缺 Phase 依赖图 | §六 顶部加 |
| 11 | 伪代码 → 实施时再写 | v2 §四 §五 给出可执行 Python（边界 + 锁 + mtime） |
| 12 | 缺权限模型 | P3 Day 2：仅本人 + admin 只读 + 审计 |

---

*Momus reviewed by Sisyphus — 2026-06-02 — v2 待用户确认*

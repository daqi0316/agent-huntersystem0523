# @ai-recruitment/context-bar

> AI 助手右上角缩略按钮 + 抽屉（数据卡片 / 上下文 / 统计 / 活动 / 审批 / 快捷操作）。
> T1 实施：从 `apps/web/components/common/context-bar` 提取为独立 monorepo 包。

## 状态

- ✅ **真正独立 npm 包**（unbuild + ESM/CJS/.d.ts + sideEffects: false）
- ✅ 包含 10 个 UI 组件 + 1 个 hook (`useGlobalShortcut`)
- ✅ 共享 store 通过 `@ai-recruitment/agent-store` 包，apps/web 同步消费
- ✅ peerDependencies 声明完整（react / zustand / next / lucide-react / clsx / tailwind-merge）
- ✅ host 业务回调通过 `ContextBar` props 注入，包内不依赖 host 私有路径

## 公共 API

```ts
import { ContextBar, useAgentStore, newMessage } from "@ai-recruitment/context-bar";

<ContextBar
  onApprovalApprove={async (approvalId) => { /* 调 host api */ }}
  onApprovalReject={async (approvalId) => { /* 调 host api */ }}
/>
```

完整 named exports（22 个）：

| Export | 说明 |
|---|---|
| `ContextBar` | 主组件（缩略按钮 + 抽屉） |
| `ContextChip` / `ContextDrawer` | 拆分子组件 |
| `DataCardItem` | 单卡片渲染 |
| `CurrentContextSection` | 当前讨论上下文 |
| `PendingApprovalSection` | 待审批（纯 UI，行为由 host 注入） |
| `QuickActionsSection` | 快捷操作 |
| `RecentActivitySection` | 最近活动 |
| `SearchBar` + `filterCards` + `EMPTY_FILTERS` | 搜索/过滤 |
| `SessionStatsSection` | 会话统计 |
| `useGlobalShortcut` | 全局快捷键 hook |
| `useAgentStore` / `selectUnreadCardCount` / `selectLatestCards` | 共享 store |
| `newMessage` | ChatMessage 工厂 |
| `parseDataCardsFromMessage` / `parseDataCardsFromMessages` | 数据卡解析 |
| `TOOL_LABELS` / `toolLabel` | 工具名 → 中文标签 |

类型导出：`DataCard` / `DataCardType` / `ChatContext` / `SessionStats` / `ChatMessage` / `ApprovalState` / `OperationPanelState` / `UploadedFile` / `ToolCallInfo` / `AgentActionInfo` / `AgentChatResponse` / `MemoryFact` / `AgentStoreState` / `ContextBarProps` / `PendingApprovalSectionProps`。

## 在 apps/web 消费（monorepo 内）

```ts
// apps/web/components/common/header.tsx
import { ContextBar, useAgentStore, newMessage } from "@ai-recruitment/context-bar";
import { api } from "@/lib/trpc";

<ContextBar
  onApprovalApprove={async (id) => { await api.post("/human-loop/approve", ...); }}
  onApprovalReject={async (id) => { await api.post("/human-loop/approve", { approved: false, ... }); }}
/>
```

`apps/web/node_modules/@ai-recruitment/context-bar` 是 symlink，源码改动后需 `corepack pnpm --filter @ai-recruitment/context-bar build` 重新打 dist。

## 在 monorepo 外消费

```bash
# 1. 安装包
pnpm add @ai-recruitment/context-bar react zustand next lucide-react clsx tailwind-merge
```

```ts
// 2. 在根 layout 注入 zustand persist（仅一次）
// apps/web 实现：在 (dashboard)/layout.tsx 用 <AgentProvider> rehydrate
// 包本身不强制要求，由 host 决定何时 hydrate
```

```css
/* 3. tailwind.config.ts 必须 scan 到包内 .tsx 组件类名 */
export default {
  content: [
    "./node_modules/@ai-recruitment/context-bar/dist/**/*.{js,cjs,mjs}",
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  // ...
};
```

**为什么不是 `./node_modules/@ai-recruitment/context-bar/src/`？**
本包 build 后 dist 是**真正独立的**（peerDeps + externals 配置），消费方应使用 dist 产物，不要直接 import src。

## 架构分层

```
┌─────────────────────────────────────────────────┐
│  Host 应用 (apps/web)                          │
│   ├─ <ContextBar onApprovalApprove={...} />   │  ← host 注入业务回调
│   ├─ useChatMessages / useChatStream           │
│   └─ api.post('/human-loop/approve', ...)      │
└──────────────────────┬──────────────────────────┘
                       │ 业务回调
┌──────────────────────▼──────────────────────────┐
│  @ai-recruitment/context-bar  (UI 纯展示)      │
│   ├─ ContextBar / Drawer / Chip                │
│   ├─ Sections (Context/Approval/Stats/...)    │
│   └─ useGlobalShortcut (⌘K/Esc)                │
└──────────────────────┬──────────────────────────┘
                       │ 共享状态
┌──────────────────────▼──────────────────────────┐
│  @ai-recruitment/agent-store  (数据层)          │
│   ├─ zustand + persist (ai-recruitment-agent-store)
│   ├─ parseDataCardsFromMessage (lib/parser)    │
│   └─ TOOL_LABELS (lib/tool-labels)              │
└─────────────────────────────────────────────────┘
```

## CSS / Tailwind 配置（重要）

**unbuild 不处理 CSS**。包内 10 个 UI 组件全用 Tailwind class，**不包含样式产物**。

消费方必须：
1. 已装 Tailwind CSS
2. `tailwind.config.ts` `content` scan 包含包 dist 路径（见上）
3. 全局有 shadcn/ui 基础变量（`--background` / `--foreground` 等 CSS 变量）

不满足以上任意一条：组件能渲染但**无样式**（裸 HTML 标签）。

## 构建

```bash
corepack pnpm --filter @ai-recruitment/context-bar build
```

输出 `dist/`：
- `index.mjs` (~42KB) — ESM
- `index.cjs` (~44KB) — CommonJS
- `index.d.ts` / `index.d.cts` / `index.d.mts` — TypeScript 类型
- `index.mjs.map` / `index.cjs.map` — sourcemap

watch 模式：
```bash
corepack pnpm --filter @ai-recruitment/context-bar dev
```

类型检查（不发 emit）：
```bash
corepack pnpm --filter @ai-recruitment/context-bar typecheck
```

清理：
```bash
corepack pnpm --filter @ai-recruitment/context-bar clean
```

## 测试

```bash
# 单元测试在 packages/agent-store
corepack pnpm --filter @ai-recruitment/agent-store exec tsx --test test/parser.test.ts
```

## 已知约束

1. **persist key**：`ai-recruitment-agent-store` 写 localStorage；多个 host 共用会冲突
2. **CSS**：依赖 host Tailwind 配置（见上）
3. **业务回调必须 host 注入**：包内不调任何 host 私有路径
4. **React 18 only**：未测 React 19（peerDep 锁 ^18.3.0）

## 升级路径

发布到 npm 时：
1. 删 `private: true`
2. 增 `repository` / `bugs` / `homepage` 字段
3. 设 `version` (semver)
4. `pnpm publish --access public`

但本仓库 `private: true`，仅 monorepo 内消费，不发布。

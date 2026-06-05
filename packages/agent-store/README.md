# @ai-recruitment/agent-store

> AI 助手共享状态层：Zustand store + DataCard 解析器 + 工具标签映射。
> 供 `@ai-recruitment/context-bar` 包与 `apps/web` 共用。

## 状态

- ✅ 真正独立 monorepo 包（unbuild + ESM/CJS/.d.ts）
- ✅ dual export 入口：`@ai-recruitment/agent-store`（store） / `./parser` / `./tool-labels`
- ✅ persist 中间件配置（`ai-recruitment-agent-store` key 保持兼容）
- ✅ 14/14 单元测试通过（`test/parser.test.ts`）

## 公共 API

```ts
import { useAgentStore, newMessage } from "@ai-recruitment/agent-store";
import { parseDataCardsFromMessage } from "@ai-recruitment/agent-store/parser";
import { TOOL_LABELS, toolLabel } from "@ai-recruitment/agent-store/tool-labels";
```

### 主入口 `./`（store）

| Export | 说明 |
|---|---|
| `useAgentStore` | Zustand store hook |
| `selectUnreadCardCount` / `selectLatestCards` | 常用 selectors |
| `newMessage` | `ChatMessage` 工厂函数（带 id + createdAt） |
| 类型：`AgentStoreState` / `DataCard` / `DataCardType` / `ChatContext` / `SessionStats` / `ChatMessage` / `ApprovalState` / `OperationPanelState` / `UploadedFile` / `ToolCallInfo` / `AgentActionInfo` / `AgentChatResponse` / `MemoryFact` | |

### 子路径 `./parser`

| Export | 说明 |
|---|---|
| `parseDataCardsFromMessage` | 单消息解析 |
| `parseDataCardsFromMessages` | 批量解析 |

### 子路径 `./tool-labels`

| Export | 说明 |
|---|---|
| `TOOL_LABELS` | 工具名 → 中文标签映射（17 个工具） |
| `toolLabel(name)` | 工具名 → 中文（fallback 到原名） |

## 在 apps/web 消费

`apps/web` 的 `package.json` 已声明 `workspace:*` 依赖，通过 symlink `apps/web/node_modules/@ai-recruitment/agent-store` 解析到本包。

```ts
// 旧 import
import { useAgentStore } from "@/stores/agent-store";
import { parseDataCardsFromMessage } from "@/lib/chat/data-card-parser";

// 新 import
import { useAgentStore } from "@ai-recruitment/agent-store";
import { parseDataCardsFromMessage } from "@ai-recruitment/agent-store/parser";
```

## persist 迁移

- **persist key 不变**：`"ai-recruitment-agent-store"`
- 旧用户 localStorage 数据自动复用，**无数据迁移**
- 仍走 `partialize: dataCards + currentContext`（最小持久化集）

## 测试

```bash
corepack pnpm --filter @ai-recruitment/agent-store exec tsx --test test/parser.test.ts
```

14 个测试覆盖：candidate_list / dashboard_stats / evaluation / jd / interview_schedule / tool hint 优先 / "other" 不产生卡片 / user 消息不解析 / error 消息不解析 / 非法 JSON 跳过 / 多 JSON 块 / messageId 反映 msg.id / 批量解析 / 空 content。

## 已知约束

- 仅支持 React 18 + zustand 4（peerDep 锁定）
- 跨包时 host 端 `useChatStream` 等 hook 仍需直接 import 本包（保持一致 import path）
- 没有跨 SSR 的额外兼容（Next.js 14 / React 18 client only 模式）

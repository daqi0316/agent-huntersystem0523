# ContextBar — 右上角缩略按钮 + 抽屉

AI 助手消息流中的结构化数据卡片（候选人列表、看板数据、搜索结果、评估、JD、面试安排）以"缩略按钮 + 抽屉"形式常驻右上角，跨页面、跨刷新可见。

## 架构

```
┌─────────────────────────────────────────────────────┐
│  Header (apps/web/components/common/header.tsx)      │
│    └─ <ContextBar /> (本模块)                        │
│         ├─ ContextChip         缩略按钮 + 角标        │
│         └─ ContextDrawer       抽屉                  │
│              └─ DataCardItem × N                     │
├─────────────────────────────────────────────────────┤
│  (dashboard)/layout.tsx                              │
│    └─ <AgentProvider>                                │
│         ├─ persist.rehydrate()                       │
│         └─ initAgentStoreSync()                      │
│              └─ BroadcastChannel (跨 tab)            │
├─────────────────────────────────────────────────────┤
│  /agent page.tsx                                     │
│    └─ useChatMessages() + useAgentContext()          │
│         └─ messages → agent-store.currentContext     │
│                                                       │
│  useChatStream.sendMessage()                         │
│    └─ parseDataCardsFromMessage() → addCard()        │
└─────────────────────────────────────────────────────┘
```

## 关键文件

| 文件 | 职责 |
|---|---|
| `index.tsx` | 容器：Chip + Drawer 编排 |
| `context-chip.tsx` | 缩略按钮（icon + 角标 + 话题副标题） |
| `context-drawer.tsx` | 抽屉（桌面右侧 / 移动端底部 sheet） |
| `data-card-item.tsx` | 单卡片渲染（5 种 type 各有 payload 预览） |
| `../../hooks/chat/use-global-shortcut.ts` | ⌘K / Esc 全局快捷键 |
| `../../hooks/chat/use-agent-context.ts` | 自动追踪 currentContext |
| `../../hooks/chat/use-agent-event-stream.tsx` | Phase 4.1 SSE 跨设备同步 |
| `../../lib/chat/data-card-parser.ts` | 助手消息 → DataCard 解析 |
| `../../lib/agent-store-sync.ts` | 多 tab BroadcastChannel 同步 |
| `../../stores/agent-store.ts` | Zustand store（persist + immer-free） |

## 数据流

```
助手回复（同一设备）
  ↓ useChatStream.sendMessage 成功
parseDataCardsFromMessage(msg)
  ↓ Omit<DataCard, 'id'|'createdAt'|'isRead'>[]
useAgentStore.getState().addCard(card) × N
  ↓
agent-store.dataCards 更新
  ↓
ContextChip 重渲染（selectUnreadCardCount）
ContextDrawer 重渲染（卡片列表）
  ↓
useAgentStore.subscribe
  ↓
BroadcastChannel.postMessage  ← 同设备多 tab
        +
后端 /agent/chat 完成后 emit_chat_response  ← 跨设备
        ↓
EventSource /agent/events 推送到所有设备
        ↓
AgentEventStreamBridge 订阅 chat_response
        ↓
parseDataCardsFromMessage → addCard × N
```

## DataCardType 识别规则

| Type | 触发条件 |
|---|---|
| `candidate_list` | 数组 + items[].name |
| `dashboard_stats` | Object + total_candidates / total_jobs / active_interviews |
| `evaluation` | Object + overall_score |
| `jd` | Object + jd_content |
| `interview_schedule` | Object + interview_id / scheduled_at |
| `search_result` | tool hint = search_candidates |
| `other` | 其它（不产生卡片） |

工具名 hint 优先于字段识别：
```ts
TOOL_HINT_TO_TYPE = {
  get_dashboard_stats: "dashboard_stats",
  search_candidates: "candidate_list",
  screen_resume: "evaluation",
  generate_jd: "jd",
  schedule_interview: "interview_schedule",
  ...
}
```

## 状态切片（agent-store）

| 字段 | 持久化 | 同步多 tab | 说明 |
|---|---|---|---|
| `dataCards` | ✅ | ✅ | 卡片列表（最多 50） |
| `currentContext` | ✅ | ✅ | 当前讨论上下文 |
| `messages` | localStorage（hook 独立） | ❌ | 由 useChatMessages 管理 |
| `approval` | ❌ | ❌ | 临时审批状态 |
| `attachment` | ❌ | ❌ | 临时附件 |
| `lastToolCalls` | ❌ | ❌ | 临时 |
| `operationPanel` | ❌ | ❌ | 临时 |

## 键盘快捷键

| 快捷键 | 行为 |
|---|---|
| ⌘K (Mac) / Ctrl+K (Win/Linux) | 打开数据看板抽屉 |
| Esc | 关闭抽屉 |
| 焦点在输入框/textarea | 快捷键自动失效 |

## a11y

- `role="dialog"` + `aria-modal="true"` + `aria-label` 标记抽屉
- `aria-hidden` 动态切换（关闭时 true）
- 打开时 focus 移到关闭按钮
- 关闭时还原 focus 到打开前元素
- ContextChip 有 `aria-label` 显示未读数

## 响应式

| Viewport | Drawer 行为 |
|---|---|
| `>= 768px` (md) | 右侧 w-96 抽屉（默认） |
| `< 768px` | 底部 sheet（w-full h-80vh rounded-t-2xl） |

## 测试

```bash
# 单元测试
npx tsx --test lib/chat/data-card-parser.test.ts
# 14/14 pass

# 端到端验证
npx tsx scripts/verify-contextbar.ts
# 13/13 pass
#   桌面：11 项
#   移动：2 项（375x667 缩略按钮可见 + 底部 sheet 形态）
```

## 扩展点（Phase 5 候选）

1. **新的数据卡片类型**：在 `data-card-parser.ts` 的 `detectType()` 添加分支 + `data-card-item.tsx` 的 `renderPayloadPreview()` 添加渲染
2. **新的抽屉 slot**：在 `context-bar/index.tsx` 增加新的 ContextDrawer 实例，注册为独立的 chip
3. **跨设备同步**：Phase 4.1（待）—— 后端 SSE → useEventSource → agent-store.setState
4. **可拖拽排序**：用 dnd-kit 给 DataCard 排序
5. **搜索/过滤**：抽屉顶部加搜索框过滤卡片

## 共存边界（用户决策）

`MemoryPanel` / `OperationPanel` / `CommandPalette` 仍由 `/agent` 页面独立控制（z-50，z-50，z-100），**不**并入 ContextBar。ContextBar 仅 z-40 接管 dataCards。

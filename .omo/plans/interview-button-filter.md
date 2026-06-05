# Plan: 面试管理 4 个功能点改为可点击 Button（Momus 修正版）

> 在原始方案基础上应用 Momus 硬伤 1-4 修正。

## 0. Context

`apps/web/app/(dashboard)/interview/page.tsx` line 406-426 的 4 个 KPI 是只读 `<Card>`，点击无反应。
改为可点击 `<Button>`，点击切换 `DataTable` 显示对应状态面试。

## 1. 目标

- 4 个 KPI 卡片改为 `<Button>`，点击切换 filter
- active filter 高亮（variant="default" vs "outline"）
- "总面试" = 不过滤 = 全部
- 不破坏 Pending Proposals / 审批历史 / 弹窗

## 2. 设计决策（Momus 修正：加"点击行为"列）

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1.a | "总面试" 按钮 | **点击行为**：reset filter = all<br>**视觉**：数字 = interviews.length | 保持 4 个按钮对称，作为默认入口 |
| D1.b | "待确认" 按钮 | **点击行为**：filter = pending<br>**视觉**：数字 = pending 数 | — |
| D1.c | "今日面试" 按钮 | **点击行为**：filter = today<br>**视觉**：数字 = today 数 | — |
| D1.d | "已完成" 按钮 | **点击行为**：filter = completed<br>**视觉**：数字 = completed 数 | — |
| D2 | Button 视觉 | `<Button variant="outline">` 包裹大数字+图标 | 零歧义按钮语义 |
| D3 | 空态 UX | DataTable 默认空态文案（"暂无数据"） | 不打扰用户 |
| D4 | 切换 filter 不滚动 | 保持位置 | 避免无谓滚动 |
| D5 | 加载状态 | 按钮显示 0（不 disabled） | 与原 Card 行为一致 |

## 3. 改动清单（单文件）

`apps/web/app/(dashboard)/interview/page.tsx`：

| # | 行号 | 改动 |
|---|---|---|
| 1 | line 3 | 加 `useMemo` import |
| 2 | line 117 后 | 加 `statusFilter` state |
| 3 | hooks 区（在所有 return 之前） | 加 `today` + `filteredInterviews` useMemo |
| 4 | line 406-426 | 4 个 Card → 4 个 Button |
| 5 | line 553 | DataTable data 用 `filteredInterviews` |

## 3.5 执行顺序（Momus 硬伤 3）

```
1. 读文件 line 100-250, 370-430 确认当前实际状态
2. 修复 §4.1 的 hooks 顺序：把 useMemo 移到 useState 之后、所有 return 之前
3. 修复 §4.2 的"今日面试" value：用 `today` 缓存不用 `new Date()`
4. 跑 `cd apps/web && npx tsc --noEmit` 验证 TypeScript
5. 浏览器访问 http://localhost:3000/interview，4 个按钮各点 1 次验证
```

## 4. 关键代码

### 4.1 hooks 区（所有 return 之前）

```tsx
// 位置：useState 之后、所有 return 之前
// today 缓存：避免按钮 count 和 filter 跨午夜不一致
const today = useMemo(() => new Date(), []);
const filteredInterviews = useMemo(() => {
  switch (statusFilter) {
    case "pending":   return interviews.filter(i => i.status === "pending");
    case "today":     return interviews.filter(i => i.rawDate && isSameDay(new Date(i.rawDate), today));
    case "completed": return interviews.filter(i => i.status === "completed");
    default:          return interviews;
  }
}, [interviews, statusFilter, today]);
```

### 4.2 4 个 Button 数组

```tsx
{([
  { key: "all",       label: "总面试",   value: interviews.length,                                                icon: Users,    color: "text-blue-600" },
  { key: "pending",   label: "待确认",   value: interviews.filter(i => i.status === "pending").length,           icon: Clock,    color: "text-amber-600" },
  { key: "today",     label: "今日面试", value: interviews.filter(i => i.rawDate && isSameDay(new Date(i.rawDate), today)).length, icon: Calendar, color: "text-violet-600" },
  { key: "completed", label: "已完成",   value: interviews.filter(i => i.status === "completed").length,         icon: Check,    color: "text-green-600" },
] as const).map(s => {
  const Icon = s.icon;
  const active = statusFilter === s.key;
  return (
    <Button
      key={s.key}
      type="button"
      variant={active ? "default" : "outline"}
      className="h-auto py-4 flex-col items-start gap-1"
      onClick={() => setStatusFilter(s.key)}
      aria-pressed={active}
    >
      <div className="flex w-full items-center justify-between">
        <span className="text-sm font-medium">{s.label}</span>
        <Icon className={`h-4 w-4 ${active ? "" : s.color}`} />
      </div>
      <span className="text-3xl font-bold">{s.value}</span>
    </Button>
  );
})}
```

### 4.3 DataTable

```tsx
<DataTable columns={columns} data={filteredInterviews as unknown as Record<string, unknown>[]} />
```

## 5. 风险评估（Momus 修正：补回滚步骤）

| 风险 | 缓解 |
|---|---|
| hooks 顺序违规 | useMemo 移至所有 return 之前 |
| 跨午夜 `new Date()` 不一致 | 缓存 `today` 用 useMemo，filter 和按钮 value 共用 |
| 失去 Card 阴影视觉 | variant="default" active 状态补视觉重量 |
| DataTable 空态不友好 | 接受默认空态文案 |

## 6. 验收标准

- [ ] 4 个按钮可点击
- [ ] 点击"总面试" → DataTable 显示全部
- [ ] 点击"待确认" → 仅 status=pending 行
- [ ] 点击"今日面试" → 仅 rawDate 是今天行
- [ ] 点击"已完成" → 仅 status=completed 行
- [ ] active 按钮 variant="default" 高亮
- [ ] aria-pressed 正确
- [ ] hooks 顺序合规（不报 React 警告）
- [ ] 加载态按钮显示 0
- [ ] 不破坏 AI 提案 / 审批历史 / 弹窗

## 7. Out of Scope

- ❌ 改 Pending Proposals 区域
- ❌ URL query 持久化 filter
- ❌ 改后端 API
- ❌ 改 DataTable 组件
- ❌ 加 i18n（已核实项目未用 i18n 框架）
- ❌ 单元测试（UI 交互可由手动验收替代）

## 8. 时间预估（Momus 修正：10-15 分钟）

| 步骤 | 时间 |
|---|---|
| 修复 hooks 位置 | 3 分钟 |
| 修"今日面试"用 today | 2 分钟 |
| TypeScript 验证 | 2 分钟 |
| 手动验收 4 个按钮 | 5-8 分钟 |
| **总计** | **12-15 分钟** |

## 9. 回滚（Momus 硬伤 4）

```bash
git revert <commit>  # 一行回滚，无 DB 影响
```

## 10. Momus 修正对照

| Momus 硬伤 | 修正方式 | 状态 |
|---|---|---|
| 1. 代码自相矛盾（today 缓存 vs new Date） | §4.1/4.2 都用 `today` | ✅ 已修正 |
| 2. D1 表述歧义 | §2 D1 表格加"点击行为"列 | ✅ 已修正 |
| 3. 执行步骤不清 | 加 §3.5 | ✅ 已修正 |
| 4. 缺回滚 | 加 §9 | ✅ 已修正 |

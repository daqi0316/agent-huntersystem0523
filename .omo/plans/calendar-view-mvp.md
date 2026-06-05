# 日历视图 Plan（Momus 4 硬伤 + 2 软伤已修）

## 0. Context

| 发现 | 详情 |
|---|---|
| 前端按钮 | `interview/page.tsx:407-410` 日历视图按钮**无 onClick** |
| 组件 | `components/features/interview/calendar-view.tsx` 18 行**占位符**（"后续实现"），未被引用 |
| 后端 API | interview 有 list/get/create/confirm，**无 calendar 端点** |
| UI 组件 | **无 Dialog/Sheet 组件**（只有 card/button/skeleton/switch/tabs 等） |
| date-fns | ✅ **已装** (`^3.6.0`) |
| 现有 modal 模式 | page.tsx line 616 用 `<div className="fixed inset-0 z-50 bg-black/40">` 自建 |

## 1. 选型

**A. 自建月视图（推荐）**：
- 复用 date-fns（已装，零新依赖）
- 自建 Sheet 弹窗（参考 page.tsx 现有 modal 模式）
- 阶段 1 MVP：半天

## 2. 阶段 1 MVP 执行（半天，5 步）

### 步骤 1：后端 list_interviews 加 date_from / date_to

**文件**：`apps/api/app/api/interviews.py` + `apps/api/app/services/interview.py`

```python
# services/interview.py:154
async def list_all(
    self,
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[dict], int]:
    query = select(Interview)
    count_query = select(func.count(Interview.id))
    if status:
        ...  # 已有
    if date_from:
        query = query.where(Interview.scheduled_at >= date_from)
        count_query = count_query.where(Interview.scheduled_at >= date_from)
    if date_to:
        query = query.where(Interview.scheduled_at < date_to)
        count_query = count_query.where(Interview.scheduled_at < date_to)
    ...

# api/interviews.py:53
async def list_interviews(
    date_from: datetime | None = Query(None, description="ISO datetime 起点（含）"),
    date_to: datetime | None = Query(None, description="ISO datetime 终点（不含）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """分页查询面试列表，可选 date_from/date_to 时间窗过滤。"""
    service = InterviewService(db)
    items, total = await service.list_all(
        skip=skip, limit=limit, status=status, date_from=date_from, date_to=date_to,
    )
    return ListResponse(items=items, total=total, skip=skip, limit=limit)
```

**向后兼容**：现有调用不传 date_from/date_to → service 用 None → 不过滤。

### 步骤 2：重写 CalendarView 组件

**文件**：`apps/web/components/features/interview/calendar-view.tsx`

**props 契约**（Momus 硬伤 2 修正）：
```tsx
interface CalendarViewProps {
  interviews: InterviewRow[];          // 已加载的面试（page.tsx 传）
  onSelectDate?: (date: Date) => void;  // 点击日期回调（page.tsx 打开 Sheet）
}
```

**视觉规范**：
- 7×6 grid（42 格：上月末/当月/下月初）
- 每格高度固定（`min-h-[6rem]`），显示日期 + 当日面试数 badge
- 非当月日期灰显（`text-muted-foreground/40`）
- 当日面试数 > 0：badge 颜色按状态（pending 黄、confirmed 蓝、completed 绿、cancelled 红）
- 标题：YYYY 年 MM 月 + 左右切换按钮
- **不使用 date-fns 太重**：只用 `new Date(year, month, 1)` / `getDay()` / `getDate()` 等原生 API

**核心实现**（简化）：
```tsx
"use client";
import { useMemo } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

export function CalendarView({ interviews, onSelectDate }: CalendarViewProps) {
  const [cursor, setCursor] = useState(new Date());
  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  
  // 6 行 × 7 列 = 42 格
  const cells = useMemo(() => {
    const firstDay = new Date(year, month, 1);
    const startOffset = firstDay.getDay(); // 0=Sun
    const start = new Date(year, month, 1 - startOffset);
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
  }, [year, month]);
  
  // 按 date (YYYY-MM-DD) 索引面试
  const byDate = useMemo(() => {
    const map = new Map<string, InterviewRow[]>();
    for (const iv of interviews) {
      if (!iv.rawDate) continue;
      const key = new Date(iv.rawDate).toISOString().slice(0, 10);
      const arr = map.get(key) ?? [];
      arr.push(iv);
      map.set(key, arr);
    }
    return map;
  }, [interviews]);
  
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => setCursor(new Date(year, month - 1, 1))}>
          <ChevronLeft />
        </Button>
        <CardTitle>{year} 年 {month + 1} 月</CardTitle>
        <Button variant="ghost" size="sm" onClick={() => setCursor(new Date(year, month + 1, 1))}>
          <ChevronRight />
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-7 gap-1">
          {["日", "一", "二", "三", "四", "五", "六"].map(d => (
            <div key={d} className="text-center text-xs text-muted-foreground p-2">{d}</div>
          ))}
          {cells.map(d => {
            const key = d.toISOString().slice(0, 10);
            const items = byDate.get(key) ?? [];
            const isCurrentMonth = d.getMonth() === month;
            return (
              <button
                key={key}
                disabled={!isCurrentMonth}
                onClick={() => onSelectDate?.(d)}
                className={cn(
                  "min-h-[6rem] p-2 border rounded text-left",
                  !isCurrentMonth && "opacity-40 cursor-not-allowed",
                  isCurrentMonth && "hover:bg-muted cursor-pointer"
                )}
              >
                <div className="text-sm font-medium">{d.getDate()}</div>
                {items.length > 0 && (
                  <Badge variant="outline" className="mt-1">
                    {items.length} 场
                  </Badge>
                )}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
```

### 步骤 3：CalendarView 点击日期 → Sheet 显示当日面试

**重要约束**：项目**无 Sheet/Dialog 组件**。**两种选择**：
- A. 新建 `components/ui/sheet.tsx`（仿 shadcn/ui）
- B. 用 page.tsx 现有 modal 模式（`<div fixed inset-0 bg-black/40>`）

**MVP 选 B**：零新组件，复用现有模式。CalendarView 接 `onSelectDate` 回调 → page.tsx 接到回调后 setSelectedDate + 打开自建 modal。

**page.tsx 新 state**：
```tsx
const [selectedDate, setSelectedDate] = useState<Date | null>(null);
const interviewsForSelectedDate = useMemo(() => {
  if (!selectedDate) return [];
  const key = selectedDate.toISOString().slice(0, 10);
  return interviews.filter(i => i.rawDate && new Date(i.rawDate).toISOString().slice(0, 10) === key);
}, [selectedDate, interviews]);
```

**Modal（自建，参考 page.tsx:616 模式）**：
```tsx
{selectedDate && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setSelectedDate(null)}>
    <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl" onClick={e => e.stopPropagation()}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold">
          {selectedDate.toLocaleDateString("zh-CN")} 的面试
        </h2>
        <button onClick={() => setSelectedDate(null)}><X /></button>
      </div>
      <DataTable columns={columns} data={interviewsForSelectedDate} />
    </div>
  </div>
)}
```

### 步骤 4：page.tsx 加 viewMode + 按钮 onClick + localStorage 持久化

**修改**：`apps/web/app/(dashboard)/interview/page.tsx`

```tsx
type ViewMode = "list" | "calendar";

// 初始值：localStorage 优先（Momus 软伤 6 修正）
const [viewMode, setViewMode] = useState<ViewMode>(() => {
  if (typeof window === "undefined") return "list";
  return (localStorage.getItem("interview_view_mode") as ViewMode) || "list";
});

// 持久化
useEffect(() => {
  localStorage.setItem("interview_view_mode", viewMode);
}, [viewMode]);

// 日历视图按钮 onClick
<Button
  variant={viewMode === "calendar" ? "default" : "outline"}
  size="sm"
  className="gap-1"
  onClick={() => setViewMode(viewMode === "calendar" ? "list" : "calendar")}
>
  <Calendar className="h-4 w-4" />
  日历视图
</Button>

// 条件渲染
{viewMode === "list" ? (
  <DataTable columns={columns} data={filteredInterviews} />
) : (
  <CalendarView
    interviews={interviews}
    onSelectDate={setSelectedDate}
  />
)}
```

**注意**：`DataTable` 仍接收 `filteredInterviews`（保留 4 个 KPI 按钮的筛选）；CalendarView 显示**全部**面试（按日期）。

### 步骤 5：测试

| 测试 | 文件 | 验证 |
|---|---|---|
| `test_list_interviews_filters_by_date` | `apps/api/tests/test_interviews_api.py`（新建或追加） | `?date_from=&date_to=` 生效；不传参 → 返全部（向后兼容） |
| `test_list_interviews_invalid_date_returns_400` | 同上 | 非法 ISO 格式返 400 |
| `test_calendar_view_renders_42_cells` | 暂**不写**（web 端测试基建未成熟） | — |

**注**：web 端单元测试基建未成熟，CalendarView 测试**留到阶段 2**（先 e2e 验证）。

## 3. 验收标准

- [ ] `list_interviews` 不传 `date_from/date_to` → 返全部（向后兼容）
- [ ] `list_interviews?date_from=2026-06-01&date_to=2026-07-01` 返当月面试
- [ ] `date_from=invalid` 返 400
- [ ] 日历视图按钮 onClick 切换列表/日历
- [ ] 刷新页面后 viewMode 持久化（localStorage）
- [ ] 月历显示 42 格（6 行 × 7 列）
- [ ] 跨月日期灰显（`opacity-40`）
- [ ] 当日面试数 badge 显示
- [ ] 点击日期 → 弹窗显示当日面试列表
- [ ] 弹窗外点击/关闭按钮 → 关闭
- [ ] 100 测试 0 回归
- [ ] 新加 2 个 API 测试通过

## 4. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 后端加 query 参数破坏现有调用 | 极低 | 中 | 现有调用不传新参数 → service None 跳过 |
| 自建日历 UX 差 | 中 | 中 | 阶段 2 评估 FullCalendar |
| viewMode localStorage 污染其他 tab | 低 | 低 | key 用 `interview_view_mode` 命名空间清晰 |
| CalendarView 没写单测 | 中 | 中 | 阶段 2 补；阶段 1 手动 e2e 验证 |
| 自建 modal UX 不一致 | 低 | 低 | 复用 page.tsx 现有 616 行模式 |

## 5. 回滚（Momus 硬伤 4 修正）

```bash
git revert <commit>  # 无 DB 改动（不加表/不加列）
# 1.1 加 query 参数：向后兼容，回滚无副作用
# 1.2-1.4 CalendarView 重写 + page.tsx 改动：纯前端
```

## 6. 文件清单

**修改**（3）：
- `apps/api/app/services/interview.py` — list_all 加 date_from/date_to
- `apps/api/app/api/interviews.py` — list_interviews 加 Query 参数
- `apps/web/app/(dashboard)/interview/page.tsx` — viewMode + CalendarView 接入 + Sheet modal

**重写**（1）：
- `apps/web/components/features/interview/calendar-view.tsx` — 替换占位符

**新建**（1）：
- `apps/api/tests/test_interviews_api.py`（或追加到现有）

**总修改/新建**：~250 行

## 7. Out of Scope（独立 PR）

- ❌ 阶段 2 增强（周/日/状态色块/URL 持久化/创建面试）
- ❌ FullCalendar 评估
- ❌ 拖拽改期
- ❌ Web 单元测试基建
- ❌ Agent 端 calendar 能力（MCP `get_schedule` 已存在）

## 8. 长期路线图

```
阶段 1（本 PR）：月视图 MVP + 后端 date 过滤
阶段 2：周/日切换 + 状态色块 + URL 持久化 + 创建面试 + web 测试
阶段 3：拖拽改期
阶段 4：评估 FullCalendar（仅在阶段 2 UX 不足时）
```

## 9. 时间预估

| 步骤 | 时间 |
|---|---|
| 1. 后端 query 参数 | 15 分钟 |
| 2. CalendarView 重写 | 1.5 小时 |
| 3. Sheet modal（自建，page.tsx 模式） | 30 分钟 |
| 4. viewMode + page.tsx 接入 | 30 分钟 |
| 5. API 测试 | 15 分钟 |
| 验证 + 调试 | 30 分钟 |
| **总计** | **3.5-4 小时** |

"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface InterviewRowLite {
  rawDate?: string;
  status: "pending" | "confirmed" | "completed" | "cancelled";
}

export interface CalendarViewProps {
  interviews: InterviewRowLite[];
  onSelectDate?: (date: Date) => void;
}

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];

function dateKey(d: Date): string {
  // YYYY-MM-DD 用本地时区（避免 toISOString 跨日）
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function CalendarView({ interviews, onSelectDate }: CalendarViewProps) {
  const [cursor, setCursor] = useState<Date>(() => new Date());
  const year = cursor.getFullYear();
  const month = cursor.getMonth();

  // 6 行 × 7 列 = 42 格
  const cells = useMemo(() => {
    const firstDay = new Date(year, month, 1);
    const startOffset = firstDay.getDay();
    const start = new Date(year, month, 1 - startOffset);
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
  }, [year, month]);

  // 按 date (YYYY-MM-DD) 索引面试
  const byDate = useMemo(() => {
    const map = new Map<string, number>();
    for (const iv of interviews) {
      if (!iv.rawDate) continue;
      const d = new Date(iv.rawDate);
      const key = dateKey(d);
      map.set(key, (map.get(key) ?? 0) + 1);
    }
    return map;
  }, [interviews]);

  const today = dateKey(new Date());

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setCursor(new Date(year, month - 1, 1))}
          aria-label="上个月"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <CardTitle className="text-base">
          {year} 年 {month + 1} 月
        </CardTitle>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setCursor(new Date(year, month + 1, 1))}
          aria-label="下个月"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-7 gap-1">
          {WEEKDAYS.map((d) => (
            <div
              key={d}
              className="text-center text-xs text-muted-foreground p-2"
            >
              {d}
            </div>
          ))}
          {cells.map((d) => {
            const key = dateKey(d);
            const count = byDate.get(key) ?? 0;
            const isCurrentMonth = d.getMonth() === month;
            const isToday = key === today;
            return (
              <button
                key={key}
                type="button"
                disabled={!isCurrentMonth}
                onClick={() => isCurrentMonth && onSelectDate?.(d)}
                className={cn(
                  "min-h-[6rem] p-2 border rounded text-left transition-colors",
                  !isCurrentMonth && "opacity-40 cursor-not-allowed",
                  isCurrentMonth && "hover:bg-muted cursor-pointer",
                  isToday && "ring-2 ring-blue-500",
                )}
              >
                <div className="text-sm font-medium">{d.getDate()}</div>
                {count > 0 && (
                  <Badge variant="outline" className="mt-1 text-xs">
                    {count} 场
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

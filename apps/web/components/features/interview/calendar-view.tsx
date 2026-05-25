"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function CalendarView() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">面试日历</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          日历组件将在后续迭代中实现
        </p>
      </CardContent>
    </Card>
  );
}

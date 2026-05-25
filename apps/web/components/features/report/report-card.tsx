"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ReportCardProps {
  title: string;
  content: string;
  score?: number;
}

export function ReportCard({ title, content, score }: ReportCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{title}</CardTitle>
          {score !== undefined && (
            <span className="text-2xl font-bold tabular-nums text-primary">
              {Math.round(score * 100)}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground whitespace-pre-wrap">{content}</p>
      </CardContent>
    </Card>
  );
}

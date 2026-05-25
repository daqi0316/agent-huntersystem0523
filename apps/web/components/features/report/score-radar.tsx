"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ScoreRadarProps {
  scores: Record<string, number>;
  className?: string;
}

export function ScoreRadar({ scores, className }: ScoreRadarProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-base">维度评分</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {Object.entries(scores).map(([dimension, score]) => (
            <div key={dimension} className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{dimension}</span>
              <div className="flex items-center gap-2">
                <div className="h-2 w-32 rounded-full bg-secondary overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${Math.round(score * 100)}%` }}
                  />
                </div>
                <span className="w-10 text-right font-medium tabular-nums">
                  {Math.round(score * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

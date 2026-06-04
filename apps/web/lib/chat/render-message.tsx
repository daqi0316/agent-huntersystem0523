"use client";

/**
 * 纯函数：把助手消息 content（含 ```json``` 块）解析为 React 节点
 * 提取自 agent/page.tsx（原 line 86-173）
 * 行为完全保持不变。
 */

import { Users } from "lucide-react";

export function renderRichContent(content: string): React.ReactNode {
  // Try to detect and format JSON blocks
  const jsonBlocks: string[] = [];
  const cleaned = content.replace(/```(?:json)?\s*([\s\S]*?)```/g, (_, json) => {
    jsonBlocks.push(json.trim());
    return `__JSON_BLOCK_${jsonBlocks.length - 1}__`;
  });

  const parts = cleaned.split(/(__JSON_BLOCK_\d+__)/);

  return parts.map((part, i) => {
    const match = part.match(/__JSON_BLOCK_(\d+)__/);
    if (match) {
      const idx = parseInt(match[1]);
      try {
        const data = JSON.parse(jsonBlocks[idx]);
        return <JsonPreview key={i} data={data} />;
      } catch {
        return (
          <p key={i} className="whitespace-pre-wrap">
            {jsonBlocks[idx]}
          </p>
        );
      }
    }
    return (
      <p key={i} className="whitespace-pre-wrap leading-relaxed">
        {part}
      </p>
    );
  });
}

function JsonPreview({ data }: { data: unknown }) {
  if (Array.isArray(data) && data.length > 0 && data[0].name) {
    // Candidate list
    return (
      <div className="grid gap-2 my-2">
        {data.slice(0, 5).map((item: any, i: number) => (
          <div
            key={i}
            className="flex items-center gap-3 rounded-lg border p-3 bg-card"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary text-sm font-medium">
              {item.name?.[0] || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{item.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {item.current_title || "—"} ·{" "}
                {item.experience_years
                  ? `${item.experience_years}年经验`
                  : ""}
                {item.current_company ? ` · ${item.current_company}` : ""}
              </p>
            </div>
            {item.skills?.length > 0 && (
              <div className="hidden sm:flex gap-1 flex-wrap">
                {item.skills.slice(0, 3).map((s: string, j: number) => (
                  <span
                    key={j}
                    className="rounded-md bg-secondary px-2 py-0.5 text-xs"
                  >
                    {s}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (data && typeof data === "object" && "overall_score" in data) {
    // Screening result
    const d = data as Record<string, any>;
    const score = d.overall_score as number;
    let color = "text-red-500";
    if (score >= 80) color = "text-green-500";
    else if (score >= 60) color = "text-amber-500";
    return (
      <div className="rounded-lg border p-4 my-2 bg-card space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold">{score}</span>
          <span className="text-sm text-muted-foreground">匹配度评分</span>
        </div>
        {d.summary && (
          <p className="text-sm text-muted-foreground">{d.summary}</p>
        )}
      </div>
    );
  }

  if (data && typeof data === "object" && "jd_content" in data) {
    const d = data as Record<string, string>;
    return (
      <div className="rounded-lg border p-4 my-2 bg-card">
        <h4 className="font-medium text-sm mb-2">{d.title}</h4>
        <div className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-6">
          {d.jd_content}
        </div>
      </div>
    );
  }

  // Default: show nothing special, the LLM summary handles it
  return null;
}

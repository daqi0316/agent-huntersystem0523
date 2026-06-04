"use client";

/**
 * ChatInput — 提取自 agent/page.tsx（原 line 648-706）
 * 包含：附件上传 + 输入框 + 发送
 * 行为完全保留。
 */

import { useState, useRef } from "react";
import { X, Paperclip, Send, FileText } from "lucide-react";
import { ResumeUpload } from "./ResumeUpload";
import type { UploadedFile } from "@/hooks/useResumeUpload";

export interface ChatInputProps {
  loading: boolean;
  onSend: (text: string, attachment: UploadedFile | null) => void;
  onOpenCommandPalette: () => void;
}

export function ChatInput({ loading, onSend, onOpenCommandPalette }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [attachment, setAttachment] = useState<UploadedFile | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "/" && input === "") {
      e.preventDefault();
      onOpenCommandPalette();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend(input, attachment);
      setInput("");
    }
  };

  const handleSendClick = () => {
    onSend(input, attachment);
    setInput("");
  };

  return (
    <div className="border-t p-4">
      {showUpload && (
        <div className="max-w-4xl mx-auto mb-3">
          <ResumeUpload
            onUploadSuccess={(file) => {
              setAttachment(file);
              setShowUpload(false);
            }}
            onCancel={() => setShowUpload(false)}
          />
        </div>
      )}
      {attachment && !showUpload && (
        <div className="flex items-center gap-2 max-w-4xl mx-auto mb-3">
          <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-sm">
            <FileText className="h-4 w-4 text-primary" />
            <span className="truncate max-w-[200px]">{attachment.filename}</span>
            <span className="text-xs text-muted-foreground">
              ({(attachment.file_size / 1024).toFixed(0)} KB)
            </span>
          </div>
          <button
            onClick={() => {
              setAttachment(null);
              setShowUpload(false);
            }}
            className="rounded-md p-1 hover:bg-accent transition-colors"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
      )}
      <div className="flex gap-3 max-w-4xl mx-auto">
        <button
          onClick={() => setShowUpload((v) => !v)}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border bg-background hover:bg-accent transition-colors"
          title="上传简历"
        >
          <Paperclip className="h-4 w-4 text-muted-foreground" />
        </button>
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的需求，例如「搜索会 React 的候选人」"
          rows={1}
          className="flex-1 resize-none rounded-xl border bg-background px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 min-h-[44px] max-h-32"
        />
        <button
          onClick={handleSendClick}
          disabled={(!input.trim() && !attachment) || loading}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground disabled:opacity-40 transition-opacity"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      <p className="text-center text-[11px] text-muted-foreground mt-2">
        按 Enter 发送 · Shift+Enter 换行
      </p>
    </div>
  );
}

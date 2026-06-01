"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  RotateCcw,
  Pause,
  Play,
  XCircle,
  RefreshCw,
  RotateCw,
  Camera,
  Bookmark,
  Plus,
  History,
  ArrowLeftRight,
  ArrowLeft,
  Trash2,
  GitFork,
  FileSearch,
  Eye,
  List,
  FileText,
  Pencil,
  UserPlus,
  ListOrdered,
  HelpCircle,
  Tag,
  Activity,
  Settings,
  Sliders,
  Bug,
  Download,
  Upload,
  CornerDownLeft,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────

interface Command {
  name: string;
  aliases: string[];
  description: string;
  category: CategoryKey;
}

type CategoryKey = "task" | "dialog" | "crud" | "system";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onSelect: (command: string) => void;
  triggerInput: string;
}

// ── Command registry ────────────────────────────────────────────────────────

const COMMANDS: Command[] = [
  // Task control (8)
  { name: "/restart", aliases: ["/r"], description: "重启当前任务", category: "task" },
  { name: "/pause", aliases: [], description: "暂停任务", category: "task" },
  { name: "/resume", aliases: [], description: "恢复已暂停的任务", category: "task" },
  { name: "/cancel", aliases: [], description: "取消当前任务", category: "task" },
  { name: "/retry", aliases: [], description: "重试上一次失败的操作", category: "task" },
  { name: "/rollback", aliases: [], description: "回滚到上一个 checkpoint", category: "task" },
  { name: "/snapshot", aliases: [], description: "创建任务快照", category: "task" },
  { name: "/checkpoint", aliases: [], description: "创建可回滚的检查点", category: "task" },

  // Dialog management (8)
  { name: "/new", aliases: ["/n"], description: "开启新对话", category: "dialog" },
  { name: "/history", aliases: [], description: "查看历史对话", category: "dialog" },
  { name: "/switch", aliases: [], description: "切换到指定对话", category: "dialog" },
  { name: "/back", aliases: [], description: "返回上一轮对话", category: "dialog" },
  { name: "/clear", aliases: [], description: "清除当前对话", category: "dialog" },
  { name: "/merge", aliases: [], description: "合并多个对话", category: "dialog" },
  { name: "/fork", aliases: [], description: "从某轮 fork 出新对话", category: "dialog" },
  { name: "/diff", aliases: ["/d"], description: "对比两个对话的差异", category: "dialog" },

  // CRUD (7)
  { name: "/read", aliases: [], description: "读取资源详情", category: "crud" },
  { name: "/list", aliases: ["/l"], description: "列出资源(候选人/职位/...)", category: "crud" },
  { name: "/search", aliases: [], description: "全文搜索", category: "crud" },
  { name: "/write", aliases: [], description: "写入字段", category: "crud" },
  { name: "/add", aliases: [], description: "新增资源", category: "crud" },
  { name: "/delete", aliases: [], description: "删除资源(需 --force 确认)", category: "crud" },
  { name: "/batch", aliases: [], description: "批量操作", category: "crud" },

  // System (8)
  { name: "/help", aliases: ["/h"], description: "显示所有命令及说明", category: "system" },
  { name: "/version", aliases: [], description: "显示 Agent 版本", category: "system" },
  { name: "/status", aliases: ["/s"], description: "显示系统运行状态", category: "system" },
  { name: "/settings", aliases: [], description: "查看/修改用户设置", category: "system" },
  { name: "/config", aliases: [], description: "查看系统配置(仅 admin)", category: "system" },
  { name: "/debug", aliases: [], description: "显示最近审计日志", category: "system" },
  { name: "/export", aliases: [], description: "导出数据为 JSON", category: "system" },
  { name: "/import", aliases: [], description: "导入 JSON 数据", category: "system" },
];

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  task: "任务控制",
  dialog: "对话管理",
  crud: "增删改查",
  system: "系统操作",
};

const CATEGORY_ORDER: CategoryKey[] = ["task", "dialog", "crud", "system"];

// ── Component ──────────────────────────────────────────────────────────────

export function CommandPalette({
  open,
  onClose,
  onSelect,
  triggerInput,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mounted, setMounted] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Memoize filtered + grouped commands
  const grouped = useMemo(() => {
    const q = query.toLowerCase().trim();
    const filtered = q
      ? COMMANDS.filter(
          (cmd) =>
            cmd.name.toLowerCase().includes(q) ||
            cmd.aliases.some((a) => a.toLowerCase().includes(q)) ||
            cmd.description.toLowerCase().includes(q)
        )
      : COMMANDS;

    const map = new Map<CategoryKey, Command[]>();
    for (const cmd of filtered) {
      if (!map.has(cmd.category)) map.set(cmd.category, []);
      map.get(cmd.category)!.push(cmd);
    }
    return map;
  }, [query]);

  const flatList = useMemo(() => {
    return CATEGORY_ORDER.flatMap((k) => grouped.get(k) ?? []);
  }, [grouped]);

  // Sync selected index to visible items
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Focus search input when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Scroll selected item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-selected="true"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  // Track mount state for portal
  useEffect(() => {
    setMounted(true);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, flatList.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = flatList[selectedIndex];
        if (cmd) {
          onSelect(cmd.name);
          onClose();
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [flatList, selectedIndex, onSelect, onClose]
  );

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  if (!mounted || !open) return null;

  return createPortal(
    <AnimatePresence>
      <motion.div
        key="backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]"
        onClick={handleBackdropClick}
      >
        {/* Palette */}
        <motion.div
          key="palette"
          initial={{ opacity: 0, scale: 0.95, y: -8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -8 }}
          transition={{ duration: 0.15, ease: "easeOut" }}
          className="w-full max-w-lg mx-4 bg-background rounded-2xl border shadow-2xl overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Search input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b">
            <Search className="h-4 w-4 text-muted-foreground shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder='搜索命令，或直接输入 "/"'
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            <kbd className="hidden sm:inline-flex h-5 items-center gap-1 rounded border bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">
              ESC
            </kbd>
          </div>

          {/* Command list */}
          <div
            ref={listRef}
            className="max-h-80 overflow-y-auto oversetch-none"
          >
            {flatList.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                没有找到匹配的命令
              </div>
            ) : (
              CATEGORY_ORDER.map((cat) => {
                const cmds = grouped.get(cat);
                if (!cmds || cmds.length === 0) return null;
                const catStartIndex = flatList.findIndex((f) => f.category === cat);

                return (
                  <div key={cat} className="py-1">
                    <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {CATEGORY_LABELS[cat]}
                    </div>
                    {cmds.map((cmd) => {
                      const globalIndex = flatList.indexOf(cmd);
                      const isSelected = globalIndex === selectedIndex;

                      return (
                        <button
                          key={cmd.name}
                          data-selected={isSelected}
                          onClick={() => {
                            onSelect(cmd.name);
                            onClose();
                          }}
                          className={cn(
                            "w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors",
                            isSelected
                              ? "bg-primary/10 text-primary"
                              : "hover:bg-accent"
                          )}
                        >
                          {/* Icon */}
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                            <CommandIcon name={cmd.name} />
                          </span>

                          {/* Content */}
                          <span className="flex-1 min-w-0">
                            <span className="font-medium">{cmd.name}</span>
                            {cmd.aliases.length > 0 && (
                              <span className="ml-2 text-[10px] text-muted-foreground">
                                {cmd.aliases.join(" ")}
                              </span>
                            )}
                            <span className="ml-2 text-muted-foreground text-xs truncate">
                              {cmd.description}
                            </span>
                          </span>

                          {/* Keyboard hint when selected */}
                          {isSelected && (
                            <span className="flex items-center gap-0.5 shrink-0">
                              <CornerDownLeft className="h-3 w-3 text-primary/60" />
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="border-t px-3 py-2 flex items-center gap-4 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <kbd className="rounded border bg-muted px-1">↑↓</kbd> 导航
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border bg-muted px-1">↵</kbd> 选择
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border bg-muted px-1">Esc</kbd> 关闭
            </span>
            <span className="ml-auto">31 个命令</span>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}

// ── Icon helper ─────────────────────────────────────────────────────────────

function CommandIcon({ name }: { name: string }) {
  const map: Record<string, React.ReactNode> = {
    "/restart": <RotateCcw className="h-3.5 w-3.5" />,
    "/pause": <Pause className="h-3.5 w-3.5" />,
    "/resume": <Play className="h-3.5 w-3.5" />,
    "/cancel": <XCircle className="h-3.5 w-3.5" />,
    "/retry": <RefreshCw className="h-3.5 w-3.5" />,
    "/rollback": <RotateCw className="h-3.5 w-3.5" />,
    "/snapshot": <Camera className="h-3.5 w-3.5" />,
    "/checkpoint": <Bookmark className="h-3.5 w-3.5" />,
    "/new": <Plus className="h-3.5 w-3.5" />,
    "/history": <History className="h-3.5 w-3.5" />,
    "/switch": <ArrowLeftRight className="h-3.5 w-3.5" />,
    "/back": <ArrowLeft className="h-3.5 w-3.5" />,
    "/clear": <Trash2 className="h-3.5 w-3.5" />,
    "/merge": <GitFork className="h-3.5 w-3.5" />,
    "/fork": <GitFork className="h-3.5 w-3.5" />,
    "/diff": <FileSearch className="h-3.5 w-3.5" />,
    "/read": <Eye className="h-3.5 w-3.5" />,
    "/list": <List className="h-3.5 w-3.5" />,
    "/search": <FileSearch className="h-3.5 w-3.5" />,
    "/write": <Pencil className="h-3.5 w-3.5" />,
    "/add": <UserPlus className="h-3.5 w-3.5" />,
    "/delete": <Trash2 className="h-3.5 w-3.5" />,
    "/batch": <ListOrdered className="h-3.5 w-3.5" />,
    "/help": <HelpCircle className="h-3.5 w-3.5" />,
    "/version": <Tag className="h-3.5 w-3.5" />,
    "/status": <Activity className="h-3.5 w-3.5" />,
    "/settings": <Settings className="h-3.5 w-3.5" />,
    "/config": <Sliders className="h-3.5 w-3.5" />,
    "/debug": <Bug className="h-3.5 w-3.5" />,
    "/export": <Download className="h-3.5 w-3.5" />,
    "/import": <Upload className="h-3.5 w-3.5" />,
  };
  return <>{map[name] ?? <Terminal className="h-3.5 w-3.5" />}</>;
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_ITEMS, APP_NAME } from "@/lib/constants";
import { useUIStore } from "@/stores/ui-store";
import {
  Activity,
  LayoutDashboard,
  Briefcase,
  Users,
  Sparkles,
  Calendar,
  FileText,
  UserCheck,
  FilePen,
  BarChart3,
  Library,
  Search,
  Server,
  Settings,
  ChevronLeft,
  Upload,
  DollarSign,
} from "lucide-react";

const iconMap: Record<string, React.ElementType> = {
  Activity,
  LayoutDashboard,
  Briefcase,
  Users,
  Sparkles,
  Calendar,
  FileText,
  UserCheck,
  FilePen,
  BarChart3,
  Library,
  Search,
  Server,
  Settings,
  Upload,
  DollarSign,
};

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  const isAgentPage = (pathname?.startsWith("/agent") && !pathname?.startsWith("/agentops")) ?? false;
  const effectivelyCollapsed = isAgentPage || sidebarCollapsed;

  return (
    <aside
      className={cn(
        "flex flex-col border-r bg-card transition-all duration-300",
        effectivelyCollapsed ? "w-16" : "w-64"
      )}
    >
      <div className="flex h-14 items-center justify-between border-b px-4">
        {!effectivelyCollapsed && (
          <span className="font-semibold text-sm truncate">{APP_NAME}</span>
        )}
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1.5 hover:bg-accent transition-colors"
          title={effectivelyCollapsed ? "展开侧栏" : "收起侧栏"}
        >
          <ChevronLeft
            className={cn(
              "h-4 w-4 transition-transform",
              effectivelyCollapsed && "rotate-180"
            )}
          />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        {NAV_ITEMS.map((item) => {
          const Icon = iconMap[item.icon];
          const isActive = pathname?.startsWith(item.href) ?? false;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {Icon && <Icon className="h-4 w-4 shrink-0" />}
              {!effectivelyCollapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

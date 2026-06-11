"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Search, ListTodo, Users, Activity } from "lucide-react";

const subNav = [
  { label: "工作台", href: "/sourcing", icon: Search },
  { label: "任务列表", href: "/sourcing/tasks", icon: ListTodo },
  { label: "候选人", href: "/sourcing/candidates", icon: Users },
  { label: "平台状态", href: "/sourcing/platforms", icon: Activity },
];

export default function SourcingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 border-b pb-2">
        {subNav.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === "/sourcing"
              ? pathname === "/sourcing"
              : pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
      {children}
    </div>
  );
}

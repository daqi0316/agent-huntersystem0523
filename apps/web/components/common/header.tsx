"use client";

import { Bell, Moon, Sun, LogOut } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const { user, logout } = useAuth();

  useEffect(() => setMounted(true), []);

  return (
    <header className="flex h-14 items-center justify-between border-b bg-card px-6">
      <div className="flex items-center gap-2">
        {user && (
          <span className="text-sm text-muted-foreground">
            {user.name}
            <span className="mx-1 text-xs">|</span>
            <span className="text-xs capitalize">{user.role}</span>
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon">
          <Bell className="h-4 w-4" />
        </Button>
        {mounted && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
        )}
        <Button variant="ghost" size="icon" onClick={logout} title="退出登录">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}

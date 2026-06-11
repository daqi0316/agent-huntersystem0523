export const APP_NAME = "AI Recruitment System";
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const NAV_ITEMS = [
  { label: "AI 助手", href: "/agent", icon: "Sparkles" },
  { label: "数据看板", href: "/dashboard", icon: "LayoutDashboard" },
  { label: "职位管理", href: "/jobs", icon: "Briefcase" },
  { label: "候选人库", href: "/candidates", icon: "Users" },
  { label: "AI初筛", href: "/screening", icon: "Sparkles" },
  { label: "面试安排", href: "/interview", icon: "Calendar" },
  { label: "评估报告", href: "/evaluation", icon: "FileText" },
  { label: "人才画像", href: "/talent-profile", icon: "UserCheck" },
  { label: "JD生成器", href: "/jd-generator", icon: "FilePen" },
  { label: "数据报表", href: "/reports", icon: "BarChart3" },
  { label: "知识库", href: "/knowledge", icon: "Library" },
  { label: "寻源管理", href: "/sourcing", icon: "Search" },
  { label: "薪酬数据库", href: "/compensation", icon: "DollarSign" },
  { label: "入职跟踪", href: "/onboarding-tracking", icon: "UserCheck" },
  { label: "客户导入", href: "/onboarding", icon: "Upload" },
  { label: "MCP 服务器", href: "/mcp-servers", icon: "Server" },
  { label: "Agent 监控", href: "/agentops", icon: "Activity" },
  { label: "系统设置", href: "/settings", icon: "Settings" },
] as const;

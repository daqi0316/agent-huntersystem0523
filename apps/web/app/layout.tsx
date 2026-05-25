import type { Metadata } from "next";
import { APP_NAME } from "@/lib/constants";
import { AuthProvider } from "@/lib/auth-context";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: {
    default: APP_NAME,
    template: `%s | ${APP_NAME}`,
  },
  description: "AI驱动的智能招聘管理系统",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="min-h-screen bg-background antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}

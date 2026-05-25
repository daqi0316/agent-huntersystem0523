import { ThemeProvider } from "next-themes";
import { Sidebar } from "@/components/common/sidebar";
import { Header } from "@/components/common/header";
import { AuthGuard } from "@/components/common/auth-guard";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <AuthGuard>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <Header />
            <main className="flex-1 overflow-y-auto p-6 bg-background">
              {children}
            </main>
          </div>
        </div>
      </AuthGuard>
    </ThemeProvider>
  );
}

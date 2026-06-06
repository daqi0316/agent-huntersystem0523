import { Toaster } from "sonner";
import { ThemeProvider } from "next-themes";
import { Sidebar } from "@/components/common/sidebar";
import { Header } from "@/components/common/header";
import { AuthGuard } from "@/components/common/auth-guard";
import { ErrorBoundary } from "@/components/common/error-boundary";
import { TelemetryBoot } from "@/components/common/telemetry-boot";
import { AgentProvider } from "@/hooks/chat/agent-context";
import { CookieConsent } from "@/components/common/cookie-consent";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <TelemetryBoot />
      <AuthGuard>
        <AgentProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <div className="flex flex-1 flex-col overflow-hidden">
              <Header />
              <main className="flex-1 overflow-y-auto p-6 bg-background">
                <ErrorBoundary>{children}</ErrorBoundary>
              </main>
            </div>
          </div>
        </AgentProvider>
      </AuthGuard>
      <Toaster
        position="top-right"
        richColors
        closeButton
        toastOptions={{ duration: 4000 }}
      />
      <CookieConsent />
    </ThemeProvider>
  );
}

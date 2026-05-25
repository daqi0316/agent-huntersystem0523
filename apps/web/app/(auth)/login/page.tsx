import type { Metadata } from "next";
import { LoginForm } from "./login-form";

export const metadata: Metadata = {
  title: "登录",
};

export default function LoginPage() {
  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">AI Recruitment System</h1>
        <p className="text-sm text-muted-foreground">登录您的账户</p>
      </div>
      <LoginForm />
    </div>
  );
}

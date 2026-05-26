"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("[ErrorBoundary]", error, errorInfo.componentStack);
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center rounded-lg border border-destructive/20 bg-destructive/5 p-8 text-center">
          <AlertTriangle className="mb-3 h-8 w-8 text-destructive" />
          <h3 className="mb-1 text-lg font-semibold">页面出现异常</h3>
          <p className="mb-4 max-w-sm text-sm text-muted-foreground">
            {this.state.error?.message || "发生了意外错误，请稍后重试"}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={this.handleRetry}
          >
            <RefreshCw className="mr-1 h-4 w-4" />
            重新加载
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}

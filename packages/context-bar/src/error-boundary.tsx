"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { getTelemetryQueue } from "@ai-recruitment/agent-store";

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  boundaryName?: string;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  onRetry?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (typeof console !== "undefined") {
      console.error("[ErrorBoundary]", this.props.boundaryName, error);
    }
    try {
      getTelemetryQueue().track("error_boundary", {
        source: this.props.boundaryName ?? "unknown",
        success: false,
      });
    } catch {
      // telemetry 自身失败不影响错误捕获
    }
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = (): void => {
    this.props.onRetry?.();
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          role="alert"
          className="flex flex-col items-center justify-center p-4 text-center text-sm text-muted-foreground"
        >
          <p className="mb-2">该区域出现异常</p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="rounded border border-border px-3 py-1 text-xs hover:bg-accent"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

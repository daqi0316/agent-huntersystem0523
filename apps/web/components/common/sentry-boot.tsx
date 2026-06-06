"use client";

import { useEffect } from "react";

interface SentryBootProps {
  dsn?: string;
  environment?: string;
  release?: string;
}

export function SentryBoot({ dsn, environment, release }: SentryBootProps) {
  useEffect(() => {
    const finalDsn = dsn || process.env.NEXT_PUBLIC_SENTRY_DSN;
    if (!finalDsn) return;
    let cancelled = false;
    // webpackIgnore 注释让编译期不解析 @sentry/nextjs（包不在时也不挂）
    // PR-7 修：@sentry/nextjs 是可选依赖，dev 环境可能未装
    import(/* webpackIgnore: true */ "@sentry/nextjs")
      .then((Sentry) => {
        if (cancelled) return;
        Sentry.init({
          dsn: finalDsn,
          environment,
          release,
          tracesSampleRate: 0.1,
        });
      })
      .catch(() => {
        // @sentry/nextjs not installed in dev, skip silently
      });
    return () => {
      cancelled = true;
    };
  }, [dsn, environment, release]);

  return null;
}

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
    import("@sentry/nextjs")
      .then((Sentry) => {
        if (cancelled) return;
        Sentry.init({
          dsn: finalDsn,
          environment: environment || process.env.NEXT_PUBLIC_SENTRY_ENV || "production",
          release: release || process.env.NEXT_PUBLIC_GIT_SHA || "unknown",
          tracesSampleRate: 0.1,
          replaysOnErrorSampleRate: 1.0,
          replaysSessionSampleRate: 0,
          beforeSendTransaction(event) {
            if (event.transaction?.includes("/api/auth/")) {
              return null;
            }
            return event;
          },
          beforeSend(event) {
            if (event.user?.email) {
              event.user.email = "[redacted]";
            }
            return event;
          },
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

declare module "@sentry/nextjs" {
  export function init(options: {
    dsn: string;
    environment?: string;
    release?: string;
    tracesSampleRate?: number;
  }): void;
}

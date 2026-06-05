"use client";

import { useEffect } from "react";
import { setTelemetryEndpoint } from "@ai-recruitment/agent-store";

export function TelemetryBoot() {
  useEffect(() => {
    const base =
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    setTelemetryEndpoint(`${base}/agent/telemetry`);
  }, []);
  return null;
}

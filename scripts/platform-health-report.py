#!/usr/bin/env python3
"""
P6-3: Platform Health Probe Aggregation Report

Parses Playwright probe log + backend health results, generates a structured markdown report.

Usage:
  python scripts/platform-health-report.py \\
    --playwright-log /tmp/playwright-probe.log \\
    --backend-results /tmp/platform-health-results.json \\
    --output /tmp/health-report.md \\
    --api-base http://localhost:8000/api/v1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


def parse_playwright_log(log_text: str) -> dict:
    """Parse Playwright JSON reporter output for pass/fail stats."""
    result = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "failures": [],
    }
    for line in log_text.splitlines():
        m = re.match(r'\s*(✓|√|ok|passed|PASSED|\[\d+).*?(\w+\.spec\.ts)?', line)
        if 'passed' in line.lower() and 'failed' not in line.lower():
            result["passed"] += 1
        elif 'failed' in line.lower():
            result["failed"] += 1
            result["failures"].append(line.strip())
    result["total"] = result["passed"] + result["failed"]
    return result


def parse_backend_results(text: str) -> dict:
    """Parse backend platform health probe JSON output."""
    result: dict = {"platforms": {}, "total": 0, "healthy": 0, "degraded": 0, "down": 0}
    if not text.strip():
        result["error"] = "no backend probe output"
        return result
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    for platform, info in data.items():
                        if isinstance(info, dict) and "status" in info:
                            result["platforms"][platform] = info
                            s = info["status"]
                            if s == "healthy":
                                result["healthy"] += 1
                            elif s == "degraded":
                                result["degraded"] += 1
                            else:
                                result["down"] += 1
                            result["total"] += 1
            except json.JSONDecodeError:
                continue
    return result


def generate_report(
    playwright: dict,
    backend: dict,
    api_base: str,
    timestamp: str,
) -> str:
    """Generate markdown health probe report."""
    lines = []
    lines.append(f"# Platform Health Probe Report")
    lines.append(f"**Generated**: {timestamp}")
    lines.append(f"**API Base**: {api_base}")
    lines.append("")

    # ── Overall summary ──
    overall = "✅ HEALTHY"
    if playwright.get("failed", 0) > 0:
        overall = "⚠️ DEGRADED (Playwright failures)"
    if backend.get("down", 0) > 0:
        overall = "❌ UNHEALTHY (Platforms down)"
    lines.append(f"## Overall: {overall}")
    lines.append("")

    # ── Playwright probe results ──
    lines.append("## Playwright Probe")
    lines.append(f"- **Total tests**: {playwright.get('total', 0)}")
    lines.append(f"- **Passed**: {playwright.get('passed', 0)}")
    lines.append(f"- **Failed**: {playwright.get('failed', 0)}")
    if playwright.get("failures"):
        lines.append("")
        lines.append("### Failures")
        for f in playwright["failures"]:
            lines.append(f"- `{f}`")
    lines.append("")

    # ── Backend platform health ──
    lines.append("## Backend Platform Health")
    if backend.get("error"):
        lines.append(f"- ⚠️ {backend['error']}")
    else:
        lines.append(f"- **Platforms checked**: {backend.get('total', 0)}")
        lines.append(f"- **Healthy**: {backend.get('healthy', 0)}")
        lines.append(f"- **Degraded**: {backend.get('degraded', 0)}")
        lines.append(f"- **Down**: {backend.get('down', 0)}")
        lines.append("")
        if backend.get("platforms"):
            lines.append("### Per-Platform Status")
            lines.append("| Platform | Status | HTTP Status | Latency (s) | Error |")
            lines.append("|----------|--------|-------------|-------------|-------|")
            for name, info in sorted(backend["platforms"].items()):
                status_icon = "✅" if info["status"] == "healthy" else "⚠️" if info["status"] == "degraded" else "❌"
                http = info.get("http_status", "-")
                lat = info.get("latency_s", "-")
                err = info.get("error", "-")
                lines.append(f"| {name} | {status_icon} {info['status']} | {http} | {lat} | {err} |")
    lines.append("")

    # ── Recommendations ──
    lines.append("## Recommendations")
    if backend.get("down", 0) > 0:
        lines.append("- 🔴 **Action required**: Some platforms are DOWN. Investigate immediately.")
    if backend.get("degraded", 0) > 0:
        lines.append("- 🟡 **Investigate**: Some platforms are degraded (HTTP 5xx).")
    if playwright.get("failed", 0) > 0:
        lines.append("- 🟡 **Investigate Playwright failures**: UI endpoints may have issues.")
    if not backend.get("platforms"):
        lines.append("- ℹ️ No platform health data collected. Ensure backend probe ran correctly.")
    if all([
        backend.get("healthy", 0) == backend.get("total", 0),
        backend.get("total", 0) > 0,
        playwright.get("failed", 0) == 0,
    ]):
        lines.append("- ✅ All systems operational. No action needed.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Platform Health Probe Report Generator")
    parser.add_argument("--playwright-log", required=True, help="Path to Playwright probe log")
    parser.add_argument("--backend-results", required=True, help="Path to backend probe JSON results")
    parser.add_argument("--output", required=True, help="Output markdown file path")
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1", help="API base URL")
    args = parser.parse_args()

    playwright_log = ""
    if os.path.exists(args.playwright_log):
        with open(args.playwright_log) as f:
            playwright_log = f.read()

    backend_text = ""
    if os.path.exists(args.backend_results):
        with open(args.backend_results) as f:
            backend_text = f.read()

    playwright = parse_playwright_log(playwright_log)
    backend = parse_backend_results(backend_text)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    report = generate_report(playwright, backend, args.api_base, timestamp)

    with open(args.output, "w") as f:
        f.write(report)

    print(f"Report written to {args.output}")
    print(report)


if __name__ == "__main__":
    main()

"""P6-13: 可访问性 (WCAG 2.2 AA) 验证 + 基础修复。

axe-core 集成 + jest-axe 单元测试 + 自动化脚本。
范围: 关键页面 (login / dashboard / onboarding / settings)。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_WEB = REPO_ROOT / "apps" / "web"

CRITICAL_PAGES = [
    "app/(auth)/login/page.tsx",
    "app/(auth)/login/login-form.tsx",
    "app/(onboarding)/welcome/page.tsx",
    "app/(onboarding)/upload/page.tsx",
    "app/(onboarding)/evaluate/page.tsx",
    "app/(dashboard)/dashboard/page.tsx",
    "app/(dashboard)/candidates/page.tsx",
    "app/(dashboard)/jobs/page.tsx",
    "app/(dashboard)/settings/page.tsx",
    "app/(dashboard)/settings/subscription/page.tsx",
    "app/(dashboard)/settings/privacy/page.tsx",
    "app/(dashboard)/audit/page.tsx",
    "app/(dashboard)/ai-appeals/page.tsx",
    "components/common/cookie-consent.tsx",
    "components/common/rate-limit-toast.tsx",
    "components/common/sentry-boot.tsx",
    "components/features/audit/audit-log-panel.tsx",
    "components/features/ai-compliance/ai-score-badge.tsx",
]


WCAG_VIOLATIONS = {
    "color-contrast": {"severity": "serious", "fix": "加 dark:bg- 或 text- 改色"},
    "label": {"severity": "critical", "fix": "加 <label htmlFor> 关联 input"},
    "button-name": {"severity": "critical", "fix": "加 aria-label"},
    "image-alt": {"severity": "critical", "fix": "加 alt= 或 aria-label"},
    "link-name": {"severity": "serious", "fix": "加 text 或 aria-label"},
    "aria-required-attr": {"severity": "critical", "fix": "加 required aria-属性"},
    "duplicate-id": {"severity": "other", "fix": "去重 id"},
    "heading-order": {"severity": "moderate", "fix": "h1→h2 顺序不能跳"},
    "html-has-lang": {"severity": "serious", "fix": "<html lang='zh-CN'>"},
    "landmark-one-main": {"severity": "moderate", "fix": "加 <main> 包裹主内容"},
    "region": {"severity": "moderate", "fix": "所有内容包在 landmark 内"},
    "aria-roles": {"severity": "serious", "fix": "用标准 role 值"},
    "tabindex": {"severity": "serious", "fix": "tabindex=0/-1 而非 >0"},
}


def check_html_lang() -> list[str]:
    issues = []
    root_layout = APPS_WEB / "app" / "layout.tsx"
    if root_layout.exists():
        content = root_layout.read_text()
        if "<html" in content and "lang=" not in content:
            issues.append("ROOT_LAYOUT_MISSING_LANG")
    return issues


def check_aria_labels() -> list[str]:
    issues = []
    for rel_path in CRITICAL_PAGES:
        p = APPS_WEB / rel_path
        if not p.exists():
            issues.append(f"MISSING_FILE: {rel_path}")
            continue
        content = p.read_text()
        if "<button" in content and "aria-label" not in content and not re.search(r">\s*[\u4e00-\u9fff]", content):
            icon_button_count = content.count('className="h-')
            if icon_button_count > 0 and "aria-label" not in content:
                issues.append(f"ICON_BUTTON_NO_LABEL: {rel_path}")
        if "<input" in content and "id=" in content and "<label" not in content:
            issues.append(f"INPUT_NO_LABEL: {rel_path}")
    return issues


def check_keyboard_nav() -> list[str]:
    issues = []
    for rel_path in CRITICAL_PAGES:
        p = APPS_WEB / rel_path
        if not p.exists():
            continue
        content = p.read_text()
        if "onClick" in content and "onKeyDown" not in content and "<button" not in content:
            if 'role="button"' in content or 'role="link"' in content:
                issues.append(f"ROLE_BUTTON_NO_KEYBOARD: {rel_path}")
    return issues


def main() -> int:
    print("P6-13 WCAG 2.2 AA 审计 (静态)")
    print("=" * 50)

    all_issues: list[str] = []
    all_issues.extend(check_html_lang())
    all_issues.extend(check_aria_labels())
    all_issues.extend(check_keyboard_nav())

    critical = [i for i in all_issues if "MISSING" in i or "ICON" in i or "INPUT" in i or "LANG" in i or "ROLE" in i]
    warnings = [i for i in all_issues if i not in critical]

    if critical:
        print(f"❌ {len(critical)} critical issues:")
        for i in critical:
            print(f"  {i}")
    if warnings:
        print(f"⚠️  {len(warnings)} warnings:")
        for i in warnings:
            print(f"  {i}")
    if not all_issues:
        print("✅ 0 critical issues found")

    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())

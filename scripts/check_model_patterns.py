"""防再发：扫 SQLAlchemy model 中的危险模式。

被 pre-commit 调用，扫描 ``apps/api/app/models/*.py``，禁止：
1. 小写 DB label 的 enum 使用 ``SAEnum(EnumClass, name=...)`` 裸调用
   — 必须用 ``app.models._base.enum_column()`` 工厂强制 ``values_callable``。
2. 生产阻塞 model（approvals / command_audit_log）中
   出现 ``UUID(as_uuid=False)`` — DB 实际是 varchar，会导致 ORM
   ``WHERE $1::UUID`` 不可比，500 报错。
3. **v1.3 新增**: ``String(36)`` 列 FK 到 uuid 表（interviews / candidates /
   applications / job_positions）— DB 是真 uuid, model 用 varchar 会导致
   INSERT 报 ``column is uuid but expression is character varying``。

**为什么只针对小写 enum？** 大写 enum（interview_status / application_status
/ job_status / user_role）DB label 与 enum name 一致，裸 ``SAEnum`` 不会
引发 500 错误。改它们是 polish 而非必须，故不强制。

退出码：
- 0 — 0 违规
- 1 — 发现违规
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 已知 DB label 为小写、必须 values_callable 的 enum 类名
LOWERCASE_DBLABEL_ENUMS = {
    "ApprovalStatus",       # approval_status: pending/approved/...
    "RecommendationType",   # recommendation_type: candidate_job_match/...
    "CandidateStatus",      # candidate_status: active/archived/...
    "InterviewRound",       # interview_round: phone_screen/... (v1.2 migration)
    "EvaluationVerdict",    # evaluation_verdict: strong_hire/... (v1.2 migration)
}

ALL_MODEL_FILES = [
    "app/models/approval.py",
    "app/models/recommendation.py",
    "app/models/candidate.py",
    "app/models/application.py",
    "app/models/interview.py",
    "app/models/job_position.py",
    "app/models/operation_log.py",
    "app/models/command_audit_log.py",
    "app/models/interview_evaluation.py",
    "app/models/user.py",
    "app/models/mcp_server.py",
    "app/models/memory_fact.py",
    "app/models/setting.py",
    "app/models/session_summary.py",
    "app/models/conversation.py",
    "app/models/_base.py",
]


def _build_saenum_pattern(enum_classes: set[str]) -> re.Pattern[str]:
    """匹配：SAEnum(<enum>, name=...) 不带 values_callable=，且 enum 类在白名单。"""
    if not enum_classes:
        return re.compile(r"(?!)")
    names = "|".join(re.escape(n) for n in sorted(enum_classes))
    return re.compile(
        rf"SAEnum\s*\(\s*(?:{names})\s*,\s*name\s*=\s*['\"][^'\"]+['\"]\s*\)"
    )


BARE_SAENUM_PATTERN = _build_saenum_pattern(LOWERCASE_DBLABEL_ENUMS)

UUID_AS_FALSE_PATTERN = re.compile(r"UUID\s*\(\s*as_uuid\s*=\s*False\s*\)")

# v1.3: String(36) FK 到 uuid 表 (interviews/candidates/applications/job_positions)
# 模式: String(36)\s*,\s*\n\s*ForeignKey\("(interviews|candidates|applications|job_positions)\.id"
# 跨多行匹配
STRING36_FK_UUID_PATTERN = re.compile(
    r"String\s*\(\s*36\s*\)\s*,\s*\n\s*ForeignKey\s*\(\s*['\"](interviews|candidates|applications|job_positions)\.id",
    re.MULTILINE,
)

# 仅扫 UUID 模式的"生产阻塞"文件
# 注：v1.3 recommendation.py FK 目标 (candidates/job_positions) DB 是 uuid,
#     UUID(as_uuid=False) 是合法类型, 不再纳入禁止
# operation_log 仅 superseded_by 列 DB 是 uuid（合法），不纳入
# application/candidate/interview/job_position 所有列 DB 是 uuid（合法），不纳入
UUID_SCAN_FILES = [
    "app/models/approval.py",
    "app/models/command_audit_log.py",
]


def scan_file(rel_path: str, pattern: re.Pattern[str], root: Path) -> list[str]:
    path = root / rel_path
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    offenders: list[str] = []
    for m in pattern.finditer(content):
        line_no = content[:m.start()].count("\n") + 1
        offenders.append(f"{rel_path}:{line_no}: {m.group()!r}")
    return offenders


def main() -> int:
    api_root = Path(__file__).resolve().parents[1] / "apps" / "api"
    all_offenders: list[str] = []

    for rel in ALL_MODEL_FILES:
        all_offenders.extend(scan_file(rel, BARE_SAENUM_PATTERN, api_root))

    for rel in UUID_SCAN_FILES:
        all_offenders.extend(scan_file(rel, UUID_AS_FALSE_PATTERN, api_root))

    # v1.3: 扫 String(36) FK 到 uuid 表
    for rel in ALL_MODEL_FILES:
        all_offenders.extend(scan_file(rel, STRING36_FK_UUID_PATTERN, api_root))

    if all_offenders:
        print("[FAIL] 发现危险 model 模式（必须修正）：", file=sys.stderr)
        for line in all_offenders:
            print(f"  {line}", file=sys.stderr)
        print("", file=sys.stderr)
        print("修正指南：", file=sys.stderr)
        print("  - SAEnum(LowercaseEnum, name=...) -> app.models._base.enum_column(LowercaseEnum, name)", file=sys.stderr)
        print("  - UUID(as_uuid=False) -> String(36)（如果 DB 实际是 varchar）", file=sys.stderr)
        print("  - String(36) FK uuid 表 -> UUID(as_uuid=False)（如果 DB 实际是 uuid）", file=sys.stderr)
        return 1

    print(
        f"[OK] {len(ALL_MODEL_FILES)} 个 SAEnum 扫描（仅小写 enum）"
        f" + {len(UUID_SCAN_FILES)} 个 UUID 扫描"
        f" + {len(ALL_MODEL_FILES)} 个 String(36) FK 扫描，均无违规"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""v1.3: check_model_patterns.py 新增 String(36) FK 到 uuid 表 反向 mismatch 测.

v1.3 修 recommendation.py: candidate_id + job_id 从 String(36) 改 UUID(as_uuid=False)
(DB 实际是 uuid). 防再发: 写测 验 check_model_patterns.py 真能抓到这种反向 mismatch.

策略:
  1. 临时写 1 个含 String(36) FK 到 candidates.id 的"违规" model 到 /tmp
  2. 调用 check_model_patterns.scan_file() 应返 1 个违规
  3. 删 /tmp 文件
  4. 验 ALL_MODEL_FILES 扫到的真 model (recommendation.py 修后) 0 违规
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_check_model_patterns_catches_string36_fk_to_uuid():
    """核心: check 应能抓 String(36) FK 到 uuid 表."""
    from scripts.check_model_patterns import STRING36_FK_UUID_PATTERN, scan_file

    bad_code = '''from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class BadModel:
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id"),
        nullable=True,
    )
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(bad_code)
        tmp_path = Path(f.name)

    try:
        offenders = scan_file(str(tmp_path.name), STRING36_FK_UUID_PATTERN, tmp_path.parent)
        assert len(offenders) == 1, f"expected 1 offender, got {len(offenders)}: {offenders}"
        assert "candidates.id" in offenders[0]
    finally:
        tmp_path.unlink()


def test_recommendation_model_passes_check():
    """v1.3 修后: recommendation.py 0 违规 (candidate_id + job_id 改 UUID(as_uuid=False))."""
    from scripts.check_model_patterns import (
        BARE_SAENUM_PATTERN,
        STRING36_FK_UUID_PATTERN,
        UUID_AS_FALSE_PATTERN,
        UUID_SCAN_FILES,
        scan_file,
    )

    api_root = Path("/Users/qixia/agent-huntersystem0523/apps/api")
    rec_path = api_root / "app/models/recommendation.py"

    offenders = scan_file(str(rec_path), BARE_SAENUM_PATTERN, api_root)
    assert len(offenders) == 0, f"BARE_SAENUM in recommendation: {offenders}"

    offenders = scan_file(str(rec_path), STRING36_FK_UUID_PATTERN, api_root)
    assert len(offenders) == 0, f"STRING36_FK_UUID in recommendation: {offenders}"

    assert str(rec_path.relative_to(api_root)) not in UUID_SCAN_FILES, (
        "recommendation.py FK 目标 (candidates/job_positions) DB 是 uuid, 不应纳入 UUID 扫描"
    )

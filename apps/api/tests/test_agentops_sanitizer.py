from typing import cast

from app.agentops.privacy.sanitizer import SanitizedValue, sanitize_metadata, sanitize_payload, stable_hash


def test_sanitize_payload_masks_pii_values():
    data = {"note": "候选人电话 13800138000，邮箱 test@example.com"}

    sanitized = cast(dict[str, SanitizedValue], sanitize_payload(data))
    note = cast(str, sanitized["note"])

    assert "13800138000" not in note
    assert "test@example.com" not in note


def test_sanitize_payload_drops_resume_text_and_file_url():
    data = {
        "resume_text": "完整简历内容",
        "file_url": "http://minio.local/resume.pdf",
        "candidate_id": "cand-1",
    }

    sanitized = cast(dict[str, SanitizedValue], sanitize_payload(data))

    assert "resume_text" not in sanitized
    assert "file_url" not in sanitized
    assert sanitized["candidate_id"] == "cand-1"


def test_sanitize_payload_hashes_contact_fields():
    data = {"email": "test@example.com", "phone": "13800138000"}

    sanitized = cast(dict[str, SanitizedValue], sanitize_payload(data))

    assert sanitized["email"] == stable_hash("test@example.com")
    assert sanitized["phone"] == stable_hash("13800138000")


def test_sanitize_metadata_returns_dict_and_masks_nested_values():
    metadata = {"candidate": {"name": "张三先生", "mobile": "13800138000"}}

    sanitized = sanitize_metadata(metadata)
    candidate = cast(dict[str, SanitizedValue], sanitized["candidate"])
    name = cast(str, candidate["name"])

    assert isinstance(sanitized, dict)
    assert "张三" not in name
    assert candidate["mobile"] == stable_hash("13800138000")

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from app.agents.pii_filter import mask_pii

SanitizeMode = Literal["mask", "hash", "drop"]
type SanitizedValue = None | bool | int | float | str | list["SanitizedValue"] | dict[str, "SanitizedValue"]

DROP_KEYS = frozenset(
    {
        "resume_text",
        "resume_content",
        "raw_resume",
        "file_url",
        "attachment_url",
        "id_card",
        "identity_card",
        "身份证",
    }
)
HASH_KEYS = frozenset({"email", "phone", "mobile", "candidate_email", "candidate_phone"})
MASK_KEYS = frozenset({"name", "candidate_name", "contact", "address", "salary", "feedback"})


def stable_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def sanitize_payload(value: object, *, default_mode: SanitizeMode = "mask") -> SanitizedValue:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        result: dict[str, SanitizedValue] = {}
        for key, item in mapping.items():
            key_text = str(key)
            if key_text.lower() in DROP_KEYS:
                continue
            result[key_text] = _sanitize_key_value(key_text, item, default_mode=default_mode)
        return result

    if isinstance(value, str):
        return _sanitize_scalar(value, mode=default_mode)

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [sanitize_payload(item, default_mode=default_mode) for item in value]

    if value is None or isinstance(value, bool | int | float):
        return value

    return str(value)


def sanitize_metadata(metadata: Mapping[str, object] | None) -> dict[str, SanitizedValue]:
    sanitized = sanitize_payload(metadata or {}, default_mode="mask")
    if isinstance(sanitized, dict):
        return sanitized
    return {}


def _sanitize_key_value(key: str, value: object, *, default_mode: SanitizeMode) -> SanitizedValue:
    normalized = key.lower()
    if normalized in DROP_KEYS:
        return None
    if normalized in HASH_KEYS:
        return stable_hash(value)
    if normalized in MASK_KEYS:
        return sanitize_payload(value, default_mode="mask")
    return sanitize_payload(value, default_mode=default_mode)


def _sanitize_scalar(value: str, *, mode: SanitizeMode) -> str:
    if mode == "drop":
        return "[已过滤]"
    if mode == "hash":
        return stable_hash(value)
    return mask_pii(value)

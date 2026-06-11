"""去重引擎 — 精确指纹 + 模糊匹配（rapidfuzz）"""
from __future__ import annotations

import hashlib
import re
from typing import Any

import redis.asyncio as redis_ai

from app.sourcing.config import sourcing_settings

try:
    from rapidfuzz import fuzz, process as fuzz_process
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


# ── 归一化 ──


def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace(" ", "").replace("\u3000", "")
    name = name.replace("·", "").replace("•", "")
    return name.lower()


_COMPANY_SUFFIXES = [
    r"(北京|上海|广州|深圳|杭州|成都|南京|武汉|西安)",
    r"(有限公司|股份有限公司|集团|科技|技术|有限|责任公司)",
    r"[（(].*?[）)]",
]


def normalize_company(company: str) -> str:
    if not company:
        return ""
    for pattern in _COMPANY_SUFFIXES:
        company = re.sub(pattern, "", company)
    return company.strip().lower()


# ── 精确指纹 ──


def generate_fingerprint(name: str, company: str, title: str) -> str:
    n_name = normalize_name(name)
    n_company = normalize_company(company)
    n_title = (title or "").strip().lower()[:20]
    raw = f"{n_name}|{n_company}|{n_title}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def is_already_crawled(redis: redis_ai.Redis, fingerprint: str, platform: str) -> bool:
    key = f"sourcing:dedup:{platform}"
    result = await redis.sismember(key, fingerprint)
    return bool(result)


async def mark_crawled(redis: redis_ai.Redis, fingerprint: str, platform: str):
    key = f"sourcing:dedup:{platform}"
    await redis.sadd(key, fingerprint)
    await redis.expire(key, 86400 * sourcing_settings.dedup_redis_ttl_days)


async def needs_refresh(redis: redis_ai.Redis, fingerprint: str, platform: str) -> bool:
    key = f"sourcing:dedup:{platform}:refresh"
    result = await redis.sismember(key, fingerprint)
    return not bool(result)


# ── 模糊去重 ──


_NAME_SIMILARITY_THRESHOLD = 85
_COMPANY_SIMILARITY_THRESHOLD = 70
_TITLE_SIMILARITY_THRESHOLD = 60
_OVERALL_CONFIDENCE_THRESHOLD = 75


def _company_token_jaccard(a: str, b: str) -> float:
    tokens_a = set(re.findall(r"[\w\u4e00-\u9fff]+", normalize_company(a)))
    tokens_b = set(re.findall(r"[\w\u4e00-\u9fff]+", normalize_company(b)))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def compute_match_confidence(existing: dict[str, Any], candidate: dict[str, Any]) -> float:
    if not _HAS_RAPIDFUZZ:
        return 0.0

    name_sim = fuzz.ratio(
        normalize_name(existing.get("name", "")),
        normalize_name(candidate.get("name", "")),
    )
    company_sim = _company_token_jaccard(
        existing.get("company", ""),
        candidate.get("company", ""),
    ) * 100
    title_sim = fuzz.token_set_ratio(
        (existing.get("title") or "").lower(),
        (candidate.get("title") or "").lower(),
    )

    if name_sim < 60:
        return 0.0

    weights = {"name": 0.5, "company": 0.3, "title": 0.2}
    score = (
        name_sim * weights["name"]
        + company_sim * weights["company"]
        + title_sim * weights["title"]
    )
    return round(score, 1)


def is_fuzzy_duplicate(
    candidate: dict[str, Any],
    existing_pool: list[dict[str, Any]],
    threshold: float = _OVERALL_CONFIDENCE_THRESHOLD,
) -> tuple[bool, float, dict[str, Any] | None]:
    if not _HAS_RAPIDFUZZ or not existing_pool:
        return False, 0.0, None

    best_score = 0.0
    best_match = None
    for existing in existing_pool:
        score = compute_match_confidence(existing, candidate)
        if score > best_score:
            best_score = score
            best_match = existing

    return best_score >= threshold, best_score, best_match


def batch_fuzzy_dedup(
    candidates: list[dict[str, Any]],
    threshold: float = _OVERALL_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    if not _HAS_RAPIDFUZZ:
        return candidates

    seen: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for c in candidates:
        is_dup, score, match = is_fuzzy_duplicate(c, seen, threshold)
        if is_dup:
            c["_dedup"] = {"is_duplicate": True, "confidence": score, "matched_id": match.get("id")}
            duplicates.append(c)
        else:
            seen.append(c)
    return seen

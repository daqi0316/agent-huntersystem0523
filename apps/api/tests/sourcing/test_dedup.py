"""Tests for dedup.py — 去重引擎"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sourcing.dedup import (
    _company_token_jaccard,
    _HAS_RAPIDFUZZ,
    batch_fuzzy_dedup,
    compute_match_confidence,
    generate_fingerprint,
    is_already_crawled,
    is_fuzzy_duplicate,
    mark_crawled,
    needs_refresh,
    normalize_company,
    normalize_name,
)


class TestNormalizeName:
    def test_empty(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""

    def test_spaces_removed(self):
        assert normalize_name("张 三") == "张三"

    def test_fullwidth_space_removed(self):
        assert normalize_name("张\u3000三") == "张三"

    def test_dots_removed(self):
        assert normalize_name("张·三") == "张三"
        assert normalize_name("张•三") == "张三"

    def test_case_insensitive(self):
        assert normalize_name("John Doe") == "johndoe"

    def test_mixed(self):
        assert normalize_name(" 李 四 ") == "李四"


class TestNormalizeCompany:
    def test_empty(self):
        assert normalize_company("") == ""
        assert normalize_company(None) == ""

    def test_city_suffix_removed(self):
        assert normalize_company("北京字节跳动") == "字节跳动"
        assert normalize_company("上海阿里巴巴") == "阿里巴巴"

    def test_corp_suffix_removed(self):
        assert normalize_company("科技有限公司") == ""
        assert normalize_company("字节跳动有限公司") == "字节跳动"

    def test_bracket_content_removed(self):
        assert normalize_company("字节跳动（中国）") == "字节跳动"
        assert normalize_company("Tencent (China)") == "tencent"

    def test_strip_and_lower(self):
        assert normalize_company("  ByteDance  ") == "bytedance"


class TestGenerateFingerprint:
    def test_same_person_same_fingerprint(self):
        fp1 = generate_fingerprint("张三", "字节跳动", "工程师")
        fp2 = generate_fingerprint("张三", "字节跳动", "工程师")
        assert fp1 == fp2

    def test_different_person_different_fingerprint(self):
        fp1 = generate_fingerprint("张三", "字节跳动", "工程师")
        fp2 = generate_fingerprint("李四", "阿里", "产品经理")
        assert fp1 != fp2

    def test_name_normalization_affects_fp(self):
        fp1 = generate_fingerprint("张 三", "字节跳动", "工程师")
        fp2 = generate_fingerprint("张三", "字节跳动", "工程师")
        assert fp1 == fp2

    def test_empty_name(self):
        fp = generate_fingerprint("", "公司", "职位")
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA256 hex

    def test_none_values(self):
        fp = generate_fingerprint(None, None, None)
        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_title_truncated(self):
        long_title = "a" * 50
        fp = generate_fingerprint("张三", "公司", long_title)
        assert isinstance(fp, str)
        assert len(fp) == 64


class TestRedisDedupFunctions:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    async def test_is_already_crawled_hit(self, mock_redis):
        mock_redis.sismember.return_value = True
        result = await is_already_crawled(mock_redis, "fp123", "github")
        assert result is True
        mock_redis.sismember.assert_called_once_with("sourcing:dedup:github", "fp123")

    async def test_is_already_crawled_miss(self, mock_redis):
        mock_redis.sismember.return_value = False
        result = await is_already_crawled(mock_redis, "fp456", "liepin")
        assert result is False

    async def test_mark_crawled(self, mock_redis):
        await mark_crawled(mock_redis, "fp789", "boss_zhipin")
        mock_redis.sadd.assert_called_once_with("sourcing:dedup:boss_zhipin", "fp789")
        mock_redis.expire.assert_called_once()

    async def test_needs_refresh_returns_true_when_not_in_set(self, mock_redis):
        mock_redis.sismember.return_value = False
        result = await needs_refresh(mock_redis, "fp123", "github")
        assert result is True

    async def test_needs_refresh_returns_false_when_in_set(self, mock_redis):
        mock_redis.sismember.return_value = True
        result = await needs_refresh(mock_redis, "fp123", "github")
        assert result is False


class TestCompanyTokenJaccard:
    def test_identical(self):
        score = _company_token_jaccard("字节跳动", "字节跳动")
        assert score == 1.0

    def test_partial_overlap(self):
        score = _company_token_jaccard("Tencent Cloud", "Tencent Games")
        assert 0 < score < 1.0

    def test_no_overlap(self):
        score = _company_token_jaccard("阿里巴巴", "腾讯")
        assert score == 0.0

    def test_empty_inputs(self):
        assert _company_token_jaccard("", "") == 0.0
        assert _company_token_jaccard("北京字节跳动", "") == 0.0

    def test_cjk_tokens(self):
        score = _company_token_jaccard("蚂蚁集团", "蚂蚁金服")
        assert score == 0.0


class TestComputeMatchConfidence:
    def test_identical(self):
        existing = {"name": "张三", "company": "字节跳动", "title": "工程师"}
        candidate = {"name": "张三", "company": "字节跳动", "title": "工程师"}
        score = compute_match_confidence(existing, candidate)
        assert score > 80

    def test_similar_name(self):
        existing = {"name": "张三", "company": "字节跳动", "title": "工程师"}
        candidate = {"name": "张三丰", "company": "字节跳动", "title": "工程师"}
        score = compute_match_confidence(existing, candidate)
        assert score > 60

    def test_different_name_below_threshold(self):
        existing = {"name": "张三", "company": "字节跳动", "title": "工程师"}
        candidate = {"name": "李四", "company": "阿里巴巴", "title": "产品经理"}
        score = compute_match_confidence(existing, candidate)
        assert score == 0.0

    def test_without_rapidfuzz(self):
        with patch("app.sourcing.dedup._HAS_RAPIDFUZZ", False):
            existing = {"name": "张三", "company": "字节跳动", "title": "工程师"}
            candidate = {"name": "张三", "company": "字节跳动", "title": "工程师"}
            score = compute_match_confidence(existing, candidate)
            assert score == 0.0


class TestIsFuzzyDuplicate:
    def test_match_above_threshold(self):
        existing = [{"name": "张三", "company": "字节跳动", "title": "工程师"}]
        candidate = {"name": "张三", "company": "字节跳动", "title": "工程师"}
        is_dup, score, match = is_fuzzy_duplicate(candidate, existing)
        assert is_dup is True
        assert score > 75
        assert match is not None

    def test_match_below_threshold(self):
        existing = [{"name": "张三", "company": "字节跳动", "title": "工程师"}]
        candidate = {"name": "王五", "company": "不同公司", "title": "其他岗位"}
        is_dup, score, match = is_fuzzy_duplicate(candidate, existing)
        assert is_dup is False
        assert match is None

    def test_empty_pool(self):
        is_dup, score, match = is_fuzzy_duplicate({"name": "张三"}, [])
        assert is_dup is False
        assert score == 0.0
        assert match is None

    def test_no_rapidfuzz(self):
        with patch("app.sourcing.dedup._HAS_RAPIDFUZZ", False):
            existing = [{"name": "张三"}]
            candidate = {"name": "张三"}
            is_dup, score, match = is_fuzzy_duplicate(candidate, existing)
            assert is_dup is False
            assert score == 0.0


class TestBatchFuzzyDedup:
    def test_basic_dedup(self):
        candidates = [
            {"name": "张三", "company": "字节跳动", "title": "工程师"},
            {"name": "张三", "company": "字节跳动", "title": "工程师"},  # duplicate
            {"name": "李四", "company": "阿里", "title": "产品"},
        ]
        result = batch_fuzzy_dedup(candidates)
        assert len(result) == 2  # one deduped
        assert result[0]["name"] == "张三"
        assert result[1]["name"] == "李四"

    def test_no_rapidfuzz(self):
        with patch("app.sourcing.dedup._HAS_RAPIDFUZZ", False):
            candidates = [
                {"name": "张三"},
                {"name": "张三"},
            ]
            result = batch_fuzzy_dedup(candidates)
            assert len(result) == 2  # no dedup without rapidfuzz

    def test_empty_list(self):
        result = batch_fuzzy_dedup([])
        assert result == []

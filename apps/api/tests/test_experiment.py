"""P6-7: A/B 测试框架 tests (分配哈希 + 显著性 + endpoint)。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.experiment import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def override_db(app, mock_db):
    from app.core.database import get_db

    async def _mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


class TestVariantAssignment:
    def test_same_key_same_variant(self):
        from app.models.experiment import assign_variant
        v1 = assign_variant("user-1", "exp1", [
            {"name": "A", "traffic_pct": 50},
            {"name": "B", "traffic_pct": 50},
        ])
        v2 = assign_variant("user-1", "exp1", [
            {"name": "A", "traffic_pct": 50},
            {"name": "B", "traffic_pct": 50},
        ])
        assert v1 == v2

    def test_distribution_within_tolerance(self):
        from app.models.experiment import assign_variant
        variants = [
            {"name": "A", "traffic_pct": 50},
            {"name": "B", "traffic_pct": 50},
        ]
        a_count = 0
        b_count = 0
        for i in range(2000):
            v = assign_variant(f"user-{i}", "exp1", variants)
            if v == "A":
                a_count += 1
            elif v == "B":
                b_count += 1
        a_pct = a_count / 2000 * 100
        b_pct = b_count / 2000 * 100
        assert 45 <= a_pct <= 55
        assert 45 <= b_pct <= 55

    def test_different_experiments_independent(self):
        from app.models.experiment import assign_variant
        variants = [{"name": "A", "traffic_pct": 50}, {"name": "B", "traffic_pct": 50}]
        a_in_exp1 = sum(1 for i in range(200) if assign_variant(f"u-{i}", "exp1", variants) == "A")
        a_in_exp2 = sum(1 for i in range(200) if assign_variant(f"u-{i}", "exp2", variants) == "A")
        assert 70 <= a_in_exp1 <= 130
        assert 70 <= a_in_exp2 <= 130

    def test_empty_variants_returns_none(self):
        from app.models.experiment import assign_variant
        assert assign_variant("u1", "exp", []) is None

    def test_unequal_split(self):
        from app.models.experiment import assign_variant
        variants = [
            {"name": "control", "traffic_pct": 80},
            {"name": "treatment", "traffic_pct": 20},
        ]
        control = 0
        for i in range(2000):
            if assign_variant(f"u-{i}", "exp", variants) == "control":
                control += 1
        pct = control / 2000 * 100
        assert 75 <= pct <= 85


class TestZTestSignificance:
    def test_clear_winner_significant(self):
        from app.models.experiment import z_test_two_proportions
        z, p = z_test_two_proportions(p1_conv=50, p1_total=100, p2_conv=80, p2_total=100)
        assert p < 0.05
        assert abs(z) > 1.96

    def test_no_difference_not_significant(self):
        from app.models.experiment import z_test_two_proportions
        z, p = z_test_two_proportions(p1_conv=50, p1_total=100, p2_conv=50, p2_total=100)
        assert p > 0.5

    def test_small_sample_returns_no_significance(self):
        from app.models.experiment import z_test_two_proportions
        z, p = z_test_two_proportions(p1_conv=5, p1_total=10, p2_conv=9, p2_total=10)
        assert p == 1.0

    def test_min_sample_size(self):
        from app.models.experiment import MIN_SAMPLE_SIZE
        assert MIN_SAMPLE_SIZE == 30


class TestExperimentEndpoints:
    def test_create_validation_total_pct(self, client, override_db, mock_db):
        resp = client.post("/experiments", json={
            "name": "cta-test",
            "variants": [
                {"name": "A", "traffic_pct": 60},
                {"name": "B", "traffic_pct": 60},
            ],
        })
        assert resp.status_code == 400

    def test_create_validation_missing_fields(self, client, override_db, mock_db):
        resp = client.post("/experiments", json={
            "name": "cta-test",
            "variants": [
                {"traffic_pct": 50},
                {"name": "B", "traffic_pct": 50},
            ],
        })
        assert resp.status_code == 400

    def test_create_validates_name_pattern(self, client, override_db, mock_db):
        resp = client.post("/experiments", json={
            "name": "Invalid Name!",
            "variants": [{"name": "A", "traffic_pct": 50}, {"name": "B", "traffic_pct": 50}],
        })
        assert resp.status_code == 422

    def test_event_validation_must_be_impression_or_conversion(self, client, override_db, mock_db):
        resp = client.post("/experiments/events?user_id=u1", json={
            "experiment_name": "cta-test",
            "event": "click",
        })
        assert resp.status_code == 422

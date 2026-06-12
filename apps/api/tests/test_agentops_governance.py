"""Tests for Governance module (P2-C Stage 13)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agentops.governance import (
    AccessPolicy,
    AuditEntry,
    AuditLog,
    RetentionConfig,
    TenantConfig,
    TenantPolicy,
    TenantPolicyStore,
    check_access,
    get_retention_days,
)
from app.agentops.governance.access_policy import VisibilityLevel


# ════════════════════════════════════════════════════════════
# RetentionConfig
# ════════════════════════════════════════════════════════════


class TestRetentionConfig:
    def test_default_values(self) -> None:
        cfg = RetentionConfig()
        assert cfg.dev_days == 7
        assert cfg.staging_days == 30
        assert cfg.prod_days == 180
        assert cfg.incident_days == 730

    def test_clamp_negative_to_zero(self) -> None:
        cfg = RetentionConfig(dev_days=-1, prod_days=-100)
        assert cfg.dev_days == 0
        assert cfg.prod_days == 0

    def test_from_dict(self) -> None:
        cfg = RetentionConfig.from_dict({"prod_days": 90, "incident_days": 365})
        assert cfg.prod_days == 90
        assert cfg.incident_days == 365
        assert cfg.dev_days == 7  # 默认

    def test_to_dict_roundtrip(self) -> None:
        cfg = RetentionConfig(dev_days=14, prod_days=90)
        data = cfg.to_dict()
        assert data["dev_days"] == 14
        assert data["prod_days"] == 90


class TestGetRetentionDays:
    def test_dev_environment(self) -> None:
        cfg = RetentionConfig(dev_days=3)
        assert get_retention_days(cfg, "development") == 3
        assert get_retention_days(cfg, "dev") == 3

    def test_prod_environment(self) -> None:
        cfg = RetentionConfig(prod_days=180)
        assert get_retention_days(cfg, "production") == 180
        assert get_retention_days(cfg, "prod") == 180

    def test_staging_environment(self) -> None:
        cfg = RetentionConfig(staging_days=30)
        assert get_retention_days(cfg, "staging") == 30
        assert get_retention_days(cfg, "stage") == 30

    def test_unknown_environment_falls_back_to_dev(self) -> None:
        cfg = RetentionConfig(dev_days=7, prod_days=180)
        assert get_retention_days(cfg, "test") == 7
        assert get_retention_days(cfg, "sandbox") == 7

    def test_incident_overrides_environment(self) -> None:
        cfg = RetentionConfig(prod_days=180, incident_days=730)
        assert get_retention_days(cfg, "production", is_incident=True) == 730
        assert get_retention_days(cfg, "dev", is_incident=True) == 730


# ════════════════════════════════════════════════════════════
# TenantPolicy
# ════════════════════════════════════════════════════════════


class TestTenantConfig:
    def test_default_values(self) -> None:
        tc = TenantConfig(tenant_id="t1")
        assert tc.tenant_id == "t1"
        assert tc.sampling_rate is None
        assert tc.privacy_level is None

    def test_sampling_rate_clamped(self) -> None:
        tc = TenantConfig(tenant_id="t1", sampling_rate=1.5)
        assert tc.sampling_rate == 1.0
        tc2 = TenantConfig(tenant_id="t2", sampling_rate=-0.5)
        assert tc2.sampling_rate == 0.0


class TestTenantPolicy:
    def test_get_set_remove(self) -> None:
        policy = TenantPolicy()
        tc = TenantConfig(tenant_id="t1", sampling_rate=0.5)
        policy.set(tc)
        assert policy.get("t1") == tc
        assert policy.get("nonexistent") is None
        assert policy.remove("t1") is True
        assert policy.remove("t1") is False

    def test_list(self) -> None:
        policy = TenantPolicy()
        policy.set(TenantConfig(tenant_id="t1"))
        policy.set(TenantConfig(tenant_id="t2"))
        assert len(policy.list()) == 2

    def test_to_dict(self) -> None:
        policy = TenantPolicy()
        policy.set(TenantConfig(tenant_id="t1", sampling_rate=0.5, privacy_level="strict"))
        data = policy.to_dict()
        assert "t1" in data
        assert data["t1"]["sampling_rate"] == 0.5
        assert data["t1"]["privacy_level"] == "strict"


class TestTenantPolicyStore:
    def test_basic_ops(self) -> None:
        store = TenantPolicyStore()
        tc = TenantConfig(tenant_id="t1")
        store.set(tc)
        assert store.get("t1") == tc
        assert store.remove("t1") is True
        assert store.list() == []

    def test_policy_property(self) -> None:
        store = TenantPolicyStore()
        assert store.policy is store._policy
        assert isinstance(store.policy, TenantPolicy)


# ════════════════════════════════════════════════════════════
# AccessPolicy
# ════════════════════════════════════════════════════════════


class TestAccessPolicy:
    def test_default_rules_created(self) -> None:
        policy = AccessPolicy()
        assert "admin" in policy.rules
        assert "operator" in policy.rules
        assert "viewer" in policy.rules
        assert policy.rules["admin"].visibility == VisibilityLevel.ALL

    def test_get_visibility(self) -> None:
        policy = AccessPolicy()
        assert policy.get_visibility("admin") == VisibilityLevel.ALL
        assert policy.get_visibility("viewer") == VisibilityLevel.TENANT
        assert policy.get_visibility("unknown") == VisibilityLevel.NONE

    def test_can_access_no_resource_filter(self) -> None:
        policy = AccessPolicy()
        assert policy.can_access("admin", "anything") is True
        assert policy.can_access("unknown", "anything") is False

    def test_can_access_with_resource_filter(self) -> None:
        policy = AccessPolicy()
        policy.rules["viewer"] = type(policy.rules["viewer"])(
            role="viewer", visibility=VisibilityLevel.TENANT, resources=["trace", "score"]
        )
        assert policy.can_access("viewer", "trace") is True
        assert policy.can_access("viewer", "config") is False

    def test_to_dict(self) -> None:
        policy = AccessPolicy()
        data = policy.to_dict()
        assert "admin" in data
        assert data["admin"]["visibility"] == "all"


class TestCheckAccess:
    def test_admin_access_everything(self) -> None:
        policy = AccessPolicy()
        assert check_access(policy, "admin", "trace") is True
        assert check_access(policy, "admin", "score") is True

    def test_unknown_role_no_access(self) -> None:
        policy = AccessPolicy()
        assert check_access(policy, "hacker", "trace") is False

    def test_visibility_requirement(self) -> None:
        policy = AccessPolicy()
        # viewer 可见 TENANT 级别，要求 ALL 时失败
        assert check_access(policy, "viewer", "trace", require_visibility=VisibilityLevel.ALL) is False
        # admin 满足 ALL 要求
        assert check_access(policy, "admin", "trace", require_visibility=VisibilityLevel.ALL) is True
        # viewer 满足 TENANT 要求
        assert check_access(policy, "viewer", "trace", require_visibility=VisibilityLevel.TENANT) is True


# ════════════════════════════════════════════════════════════
# AuditLog
# ════════════════════════════════════════════════════════════


class TestAuditLog:
    def test_record_entry(self) -> None:
        log = AuditLog()
        entry = log.record("admin", "update", "sampling", "default")
        assert isinstance(entry, AuditEntry)
        assert entry.actor == "admin"
        assert entry.action == "update"
        assert entry.resource == "sampling"
        assert entry.resource_id == "default"
        assert isinstance(entry.timestamp, datetime)

    def test_count_increases(self) -> None:
        log = AuditLog()
        assert log.count() == 0
        log.record("admin", "update", "sampling", "default")
        assert log.count() == 1

    def test_query_all(self) -> None:
        log = AuditLog()
        log.record("admin", "update", "sampling", "default")
        log.record("operator", "create", "governance", "tenant-1")
        results = log.query()
        assert len(results) == 2

    def test_query_filter_by_actor(self) -> None:
        log = AuditLog()
        log.record("admin", "update", "sampling", "default")
        log.record("operator", "create", "governance", "tenant-1")
        results = log.query(actor="admin")
        assert len(results) == 1
        assert results[0].actor == "admin"

    def test_query_filter_by_action(self) -> None:
        log = AuditLog()
        log.record("admin", "update", "sampling", "default")
        log.record("admin", "create", "sampling", "custom")
        results = log.query(action="create")
        assert len(results) == 1

    def test_query_filter_by_resource(self) -> None:
        log = AuditLog()
        log.record("admin", "update", "sampling", "default")
        log.record("admin", "update", "privacy", "pii-rules")
        results = log.query(resource="privacy")
        assert len(results) == 1

    def test_query_pagination(self) -> None:
        log = AuditLog()
        for i in range(10):
            log.record(f"user-{i}", "update", "sampling", f"config-{i}")
        results = log.query(limit=3, offset=5)
        assert len(results) == 3
        assert results[0].resource_id == "config-5"

    def test_clear(self) -> None:
        log = AuditLog()
        log.record("admin", "update", "sampling", "default")
        assert log.count() == 1
        log.clear()
        assert log.count() == 0

    def test_max_entries_trims_old(self) -> None:
        log = AuditLog(max_entries=5)
        for i in range(10):
            log.record(f"user-{i}", "update", "sampling", f"config-{i}")
        assert log.count() == 5
        # 应保留后 5 条 (index 5-9)
        results = log.query()
        assert results[0].resource_id == "config-5"

    def test_export_csv(self) -> None:
        log = AuditLog()
        log.record("admin", "update", "sampling", "default", detail="changed rate")
        csv = log.export_csv()
        assert csv.startswith("timestamp,actor,action,resource,resource_id,detail")
        assert "admin,update,sampling,default" in csv
        assert "changed rate" in csv

    def test_record_with_previous_current(self) -> None:
        log = AuditLog()
        entry = log.record(
            actor="admin",
            action="update",
            resource="sampling",
            resource_id="default",
            previous='{"rate": 0.1}',
            current='{"rate": 0.5}',
        )
        assert entry.previous is not None
        assert "0.1" in entry.previous
        assert entry.current is not None
        assert "0.5" in entry.current

"""Tests for orchestrator.py — RecoveryExecutor + SourcingOrchestrator"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sourcing.orchestrator import RecoveryExecutor, SourcingOrchestrator


# ════════════════════════════════════════════════
# RecoveryExecutor
# ════════════════════════════════════════════════

class TestRecoveryExecutor:
    @pytest.fixture
    def executor(self):
        pool = MagicMock()
        pool.report_failure = AsyncMock()
        pool.report_success = AsyncMock()
        acct = MagicMock()
        acct.rotate = AsyncMock()
        return RecoveryExecutor(proxy_pool=pool, account_manager=acct)

    # ── _classify_error ──

    @pytest.mark.parametrize("error_msg,expected", [
        ("IP blocked: 403 forbidden", "IP_BANNED"),
        ("HTTP 403 - Forbidden", "IP_BANNED"),
        ("受限访问", "IP_BANNED"),
        ("Your IP has been banned", "IP_BANNED"),
        ("login required - 未登录", "ACCOUNT_BANNED"),
        ("account suspended", "ACCOUNT_BANNED"),
        ("auth failed", "ACCOUNT_BANNED"),
        ("429 Too Many Requests", "RATE_LIMITED"),
        ("rate limit exceeded", "RATE_LIMITED"),
        ("访问太频繁", "RATE_LIMITED"),
        ("quota exceeded", "QUOTA_EXCEEDED"),
        ("配额已用完", "QUOTA_EXCEEDED"),
        ("timed out after 30s", "TIMEOUT"),
        ("timeout", "TIMEOUT"),
        ("parse error: cannot find element", "PARSE_ERROR"),
        ("解析候选人列表失败", "PARSE_ERROR"),
        ("unknown error", "RETRY"),
    ])
    def test_classify_error(self, executor, error_msg, expected):
        assert executor._classify_error(error_msg) == expected

    # ── _apply_strategy ──

    async def test_apply_strategy_switch_proxy(self, executor):
        result = MagicMock()
        result.proxy_used = "http://proxy:8080"
        result.error_message = "IP banned"
        await executor._apply_strategy("switch_proxy", "liepin", result, MagicMock())
        executor.proxy_pool.report_failure.assert_called_once()

    async def test_apply_strategy_switch_account(self, executor):
        result = MagicMock()
        result.proxy_used = None
        await executor._apply_strategy("switch_account", "liepin", result, MagicMock())
        executor.account_manager.rotate.assert_called_once()

    async def test_apply_strategy_backoff_is_noop(self, executor):
        result = MagicMock()
        await executor._apply_strategy("backoff", "liepin", result, MagicMock())
        executor.proxy_pool.report_failure.assert_not_called()
        executor.account_manager.rotate.assert_not_called()

    # ── execute (basic) ──

    async def test_execute_success_first_attempt(self, executor):
        result = MagicMock()
        result.success = True
        result.proxy_used = "http://proxy:8080"
        result.rate_limit_info = {}

        with patch("app.sourcing.orchestrator.load_platform_config_from_db", AsyncMock(return_value={})):
            with patch("app.sourcing.orchestrator.get_adapter") as mock_get:
                adapter_cls = MagicMock()
                adapter_instance = AsyncMock()
                adapter_instance.search.return_value = result
                adapter_cls.return_value = adapter_instance
                mock_get.return_value = adapter_cls

                final = await executor.execute("liepin", "python工程师")
                assert final.success is True
                executor.proxy_pool.report_success.assert_called_once()

    async def test_execute_all_retries_exhausted(self, executor):
        result = MagicMock()
        result.success = False
        result.error_message = "timeout"
        result.captcha_triggered = False
        result.proxy_used = None

        with patch("app.sourcing.orchestrator.load_platform_config_from_db", AsyncMock(return_value={})):
            with patch("app.sourcing.orchestrator.get_adapter") as mock_get:
                adapter_cls = MagicMock()
                adapter_instance = AsyncMock()
                adapter_instance.search.return_value = result
                adapter_cls.return_value = adapter_instance
                mock_get.return_value = adapter_cls

                final = await executor.execute("liepin", "python工程师")
                assert final.success is False
                assert "All retries exhausted" in (final.error_message or "")

    async def test_execute_not_implemented(self, executor):
        with patch("app.sourcing.orchestrator.load_platform_config_from_db", AsyncMock(return_value={})):
            with patch("app.sourcing.orchestrator.get_adapter") as mock_get:
                adapter_cls = MagicMock()
                adapter_instance = AsyncMock()
                adapter_instance.search.side_effect = NotImplementedError()
                adapter_cls.return_value = adapter_instance
                mock_get.return_value = adapter_cls

                final = await executor.execute("unknown", "test")
                assert final.success is False
                assert final.error_message == "not_implemented"


# ════════════════════════════════════════════════
# SourcingOrchestrator
# ════════════════════════════════════════════════

class TestSourcingOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        db = AsyncMock()
        redis = AsyncMock()
        return SourcingOrchestrator(db=db, redis=redis)

    # ── _make_fingerprint ──

    def test_make_fingerprint_from_name_company_title(self, orchestrator):
        fp = orchestrator._make_fingerprint({
            "name": "张三",
            "company": "字节跳动",
            "title": "工程师",
        })
        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_make_fingerprint_with_username_fallback(self, orchestrator):
        fp = orchestrator._make_fingerprint({
            "username": "zhangsan",
            "company": "字节跳动",
        })
        assert isinstance(fp, str)

    def test_make_fingerprint_empty(self, orchestrator):
        fp = orchestrator._make_fingerprint({})
        assert isinstance(fp, str)

    # ── get_task ──

    async def test_get_task_found(self, orchestrator):
        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        orchestrator.db.execute = AsyncMock(return_value=mock_result)

        task = await orchestrator.get_task("task-123")
        assert task is mock_task

    async def test_get_task_not_found(self, orchestrator):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        orchestrator.db.execute = AsyncMock(return_value=mock_result)

        task = await orchestrator.get_task("nonexistent")
        assert task is None

    # ── get_task_list ──

    async def test_get_task_list(self, orchestrator):
        mock_tasks = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks
        orchestrator.db.execute = AsyncMock(return_value=mock_result)
        # count query returns 2
        orchestrator.db.execute.return_value = mock_result

        tasks, total = await orchestrator.get_task_list(status="running", page=1, page_size=10)
        assert tasks == mock_tasks

    # ── cancel_task ──

    async def test_cancel_task_running(self, orchestrator):
        task = MagicMock()
        task.status = "running"
        orchestrator.get_task = AsyncMock(return_value=task)

        result = await orchestrator.cancel_task("task-123")
        assert result is True
        assert task.status == "cancelled"
        orchestrator.db.commit.assert_called_once()

    async def test_cancel_task_already_completed(self, orchestrator):
        task = MagicMock()
        task.status = "completed"
        orchestrator.get_task = AsyncMock(return_value=task)

        result = await orchestrator.cancel_task("task-123")
        assert result is False
        orchestrator.db.commit.assert_not_called()

    async def test_cancel_task_not_found(self, orchestrator):
        orchestrator.get_task = AsyncMock(return_value=None)

        result = await orchestrator.cancel_task("nonexistent")
        assert result is False

    # ── update_prometheus_gauges ──

    def test_update_prometheus_gauges(self, orchestrator):
        with patch("app.sourcing.orchestrator.proxy_pool_size") as mock_gauge:
            orchestrator.update_prometheus_gauges(proxy_health={"premium": 5, "standard": 10})
            mock_gauge.labels.assert_called()

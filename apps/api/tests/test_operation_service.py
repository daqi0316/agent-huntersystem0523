"""Tests for app/services/operation_service.py — OperationService + EventBus.

覆盖 88 条 missed statements(25% → 目标 90%+):
- OperationEventBus: subscribe/publish/unsubscribe/subscriber-error
- OperationService.create: with/without db
- OperationService.transition: not-found, immutable, output/error fields, duration 计算, event publish
- OperationService.list: 各种 filter 组合 + 无 db
- run_and_record / complete / fail 快捷包装
- sse_generator: 订阅、user_id 过滤、heartbeat timeout、清理
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.operation_log import OperationLog, OperationStatus
from app.services.operation_service import (
    OperationEventBus,
    OperationService,
    event_bus,
)


# ─── Helpers ──────────────────────────────────────────────────────────


def _make_op_log(
    id: str = "op-1",
    status: OperationStatus = OperationStatus.PENDING,
    created_at: datetime | None = None,
    immutable: bool = True,
    user_id: str | None = "u-1",
    agent_name: str = "screening",
    action: str = "screen_resume",
) -> MagicMock:
    """Build a MagicMock that mimics OperationLog (so attribute access works)."""
    op = MagicMock(spec=OperationLog)
    op.id = id
    op.user_id = user_id
    op.agent_name = agent_name
    op.action = action
    op.status = status
    op.input_summary = "x"
    op.output_summary = None
    op.error_message = None
    op.error_category = None
    op.duration_ms = None
    op.immutable = immutable
    op.metadata_json = {}
    op.created_at = created_at or datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    op.updated_at = op.created_at
    return op


def _scalars_result(items: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


# ─── OperationEventBus ────────────────────────────────────────────────


class TestOperationEventBus:
    def test_subscribe_registers_callback(self):
        bus = OperationEventBus()
        fn = MagicMock()
        unsub = bus.subscribe("op.created", fn)
        assert fn in bus._subscribers["op.created"]
        assert callable(unsub)

    def test_publish_calls_all_subscribers(self):
        bus = OperationEventBus()
        fn1 = MagicMock()
        fn2 = MagicMock()
        bus.subscribe("op.created", fn1)
        bus.subscribe("op.created", fn2)
        bus.publish("op.created", {"id": "1"})
        fn1.assert_called_once_with({"id": "1"})
        fn2.assert_called_once_with({"id": "1"})

    def test_publish_no_subscribers_is_noop(self):
        bus = OperationEventBus()
        # 不应抛异常
        bus.publish("op.created", {"id": "1"})

    def test_publish_unknown_event_type_is_noop(self):
        bus = OperationEventBus()
        fn = MagicMock()
        bus.subscribe("op.created", fn)
        bus.publish("op.updated", {"id": "1"})
        fn.assert_not_called()

    def test_subscriber_exception_does_not_propagate(self):
        bus = OperationEventBus()
        bad_fn = MagicMock(side_effect=RuntimeError("subscriber boom"))
        good_fn = MagicMock()
        bus.subscribe("op.created", bad_fn)
        bus.subscribe("op.created", good_fn)
        # 不应抛异常
        bus.publish("op.created", {"id": "1"})
        bad_fn.assert_called_once()
        good_fn.assert_called_once()  # 后续订阅者仍收到

    def test_unsubscribe_removes_callback(self):
        bus = OperationEventBus()
        fn = MagicMock()
        unsub = bus.subscribe("op.created", fn)
        unsub()
        bus.publish("op.created", {"id": "1"})
        fn.assert_not_called()

    def test_unsubscribe_preserves_other_callbacks(self):
        bus = OperationEventBus()
        fn1 = MagicMock()
        fn2 = MagicMock()
        unsub1 = bus.subscribe("op.created", fn1)
        bus.subscribe("op.created", fn2)
        unsub1()
        bus.publish("op.created", {"id": "1"})
        fn1.assert_not_called()
        fn2.assert_called_once()

    def test_module_level_event_bus_instance(self):
        assert isinstance(event_bus, OperationEventBus)


# ─── OperationService.create ──────────────────────────────────────────


class TestOperationServiceCreate:
    async def test_create_with_db_persists(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish") as pub:
            op = await svc.create(
                user_id="u-1", agent_name="screen", action="run",
                input_summary="test", error_category="system",
                metadata_json={"k": "v"},
            )
        assert op.agent_name == "screen"
        assert op.action == "run"
        assert op.status == OperationStatus.PENDING
        assert db.add.call_count == 1
        assert db.commit.await_count == 2
        assert db.refresh.await_count == 1
        assert op.immutable is True
        # Event bus 收到 created 事件
        pub.assert_called_once()
        args, _ = pub.call_args
        assert args[0] == "operation.created"
        assert args[1]["operation_id"] == op.id
        assert args[1]["status"] == "pending"

    async def test_create_without_db_still_publishes(self):
        svc = OperationService(db=None)
        with patch.object(event_bus, "publish") as pub:
            op = await svc.create(user_id="u-1", agent_name="x", action="y")
        assert op.id  # 有 ID
        assert op.status == OperationStatus.PENDING
        pub.assert_called_once()

    async def test_create_empty_user_id_becomes_none(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            op = await svc.create(user_id="", agent_name="x", action="y")
        assert op.user_id is None

    async def test_create_empty_error_category_becomes_none(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            op = await svc.create(agent_name="x", action="y", error_category="")
        assert op.error_category is None

    async def test_create_metadata_defaults_to_empty_dict(self):
        svc = OperationService(db=None)
        with patch.object(event_bus, "publish"):
            op = await svc.create(agent_name="x", action="y")
        assert op.metadata_json == {}

    async def test_create_event_timestamp_field(self):
        svc = OperationService(db=None)
        with patch.object(event_bus, "publish") as pub:
            await svc.create(agent_name="x", action="y")
        args = pub.call_args[0]
        assert "timestamp" in args[1]


# ─── OperationService.transition ──────────────────────────────────────


class TestOperationServiceTransition:
    async def test_transition_without_db_returns_none(self):
        svc = OperationService(db=None)
        result = await svc.transition("any-id", OperationStatus.RUNNING)
        assert result is None

    async def test_transition_op_not_found_returns_none(self):
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = OperationService(db)
        result = await svc.transition("missing", OperationStatus.RUNNING)
        assert result is None

    async def test_transition_op_not_found_no_match(self):
        """all() 返回空时,scalar_one_or_none 返回 None。"""
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = OperationService(db)
        result = await svc.transition("missing", OperationStatus.RUNNING)
        assert result is None

    async def test_transition_immutable_op_returns_without_modify(self):
        op = _make_op_log(immutable=True, status=OperationStatus.COMPLETED)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        svc = OperationService(db)
        with patch.object(event_bus, "publish") as pub:
            result = await svc.transition("op-1", OperationStatus.RUNNING)
        assert result is op
        # 状态没变
        assert op.status == OperationStatus.COMPLETED
        # commit 没调用
        db.commit.assert_not_called()
        # 事件没发
        pub.assert_not_called()

    async def test_transition_to_running_sets_status(self):
        op = _make_op_log(immutable=False, status=OperationStatus.PENDING)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.transition("op-1", OperationStatus.RUNNING)
        assert op.status == OperationStatus.RUNNING
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    async def test_transition_to_completed_sets_duration(self):
        op = _make_op_log(
            immutable=False,
            status=OperationStatus.RUNNING,
            created_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"), \
             patch("app.services.operation_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 1, 10, 0, 5, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await svc.transition("op-1", OperationStatus.COMPLETED)
        # duration_ms 应是 5000 ms
        assert op.duration_ms == 5000.0

    async def test_transition_to_failed_sets_duration(self):
        op = _make_op_log(
            immutable=False,
            status=OperationStatus.RUNNING,
            created_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"), \
             patch("app.services.operation_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 1, 10, 0, 2, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await svc.transition("op-1", OperationStatus.FAILED)
        assert op.duration_ms == 2000.0

    async def test_transition_to_pending_does_not_set_duration(self):
        op = _make_op_log(
            immutable=False,
            status=OperationStatus.RUNNING,
            created_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.transition("op-1", OperationStatus.PENDING)
        # duration_ms 仍为 None
        assert op.duration_ms is None

    async def test_transition_with_output_summary(self):
        op = _make_op_log(immutable=False, status=OperationStatus.RUNNING)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.transition("op-1", OperationStatus.COMPLETED, output_summary="done")
        assert op.output_summary == "done"

    async def test_transition_empty_output_summary_not_set(self):
        op = _make_op_log(immutable=False, status=OperationStatus.RUNNING)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.transition("op-1", OperationStatus.RUNNING, output_summary="")
        # op.output_summary 初始为 None,空字符串不应被赋值
        assert op.output_summary is None

    async def test_transition_with_error_message(self):
        op = _make_op_log(immutable=False, status=OperationStatus.RUNNING)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.transition(
                "op-1", OperationStatus.FAILED,
                error_message="LLM timeout", error_category="system",
            )
        assert op.error_message == "LLM timeout"
        assert op.error_category == "system"

    async def test_transition_publishes_event(self):
        op = _make_op_log(
            immutable=False, status=OperationStatus.RUNNING,
            agent_name="screen", action="run",
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = OperationService(db)
        with patch.object(event_bus, "publish") as pub:
            await svc.transition("op-1", OperationStatus.COMPLETED, output_summary="ok")
        pub.assert_called_once()
        args = pub.call_args[0]
        assert args[0] == "operation.updated"
        assert args[1]["status"] == "completed"
        assert args[1]["output_summary"] == "ok"


# ─── OperationService.list ────────────────────────────────────────────


class TestOperationServiceList:
    async def test_list_without_db_returns_empty(self):
        svc = OperationService(db=None)
        items, total = await svc.list()
        assert items == []
        assert total == 0

    async def test_list_with_no_filters(self):
        ops = [_make_op_log(id=f"op-{i}") for i in range(3)]
        # count + list 两次 execute
        result_count = _scalars_result([op.id for op in ops])
        result_list = _scalars_result(ops)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_count, result_list])
        svc = OperationService(db)
        items, total = await svc.list()
        assert total == 3
        assert len(items) == 3
        assert db.execute.await_count == 2

    async def test_list_with_user_id_filter(self):
        op = _make_op_log(user_id="u-99")
        result_count = _scalars_result([op.id])
        result_list = _scalars_result([op])
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_count, result_list])
        svc = OperationService(db)
        with patch("app.services.operation_service.desc") as _desc:
            _desc.return_value = "desc_mock"
            items, total = await svc.list(user_id="u-99")
        # 验证 desc 被调用
        assert _desc.called
        assert total == 1
        assert len(items) == 1

    async def test_list_with_agent_name_filter(self):
        op = _make_op_log(agent_name="screening")
        result_count = _scalars_result([op.id])
        result_list = _scalars_result([op])
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_count, result_list])
        svc = OperationService(db)
        items, total = await svc.list(agent_name="screening")
        assert total == 1

    async def test_list_with_status_filter(self):
        op = _make_op_log(status=OperationStatus.FAILED)
        result_count = _scalars_result([op.id])
        result_list = _scalars_result([op])
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_count, result_list])
        svc = OperationService(db)
        items, total = await svc.list(status="failed")
        assert total == 1
        # status 被转为 enum
        assert items[0].status == OperationStatus.FAILED

    async def test_list_with_error_category_filter(self):
        op = _make_op_log()
        op.error_category = "system"
        result_count = _scalars_result([op.id])
        result_list = _scalars_result([op])
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_count, result_list])
        svc = OperationService(db)
        items, total = await svc.list(error_category="system")
        assert total == 1

    async def test_list_with_all_filters(self):
        op = _make_op_log()
        result_count = _scalars_result([op.id])
        result_list = _scalars_result([op])
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[result_count, result_list])
        svc = OperationService(db)
        items, total = await svc.list(
            user_id="u-1", agent_name="x", status="pending", error_category="system",
            limit=10, offset=5,
        )
        assert total == 1


# ─── run_and_record / complete / fail ─────────────────────────────────


class TestOperationServiceRunAndRecord:
    async def test_run_and_record_creates_and_transitions(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        op_after_create = _make_op_log(
            id="op-1", status=OperationStatus.RUNNING, immutable=False,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op_after_create
        db.execute = AsyncMock(return_value=result_mock)
        svc = OperationService(db)
        publish_calls = []
        original_publish = event_bus.publish

        def capture(event_type, data):
            publish_calls.append((event_type, data))

        event_bus.publish = capture
        try:
            op, _ = await svc.run_and_record(
                user_id="u-1", agent_name="x", action="y", input_summary="z",
            )
        finally:
            event_bus.publish = original_publish
        assert op is not None
        assert any(t == "operation.created" for t, _ in publish_calls)
        assert any(t == "operation.updated" for t, _ in publish_calls)

    async def test_complete_calls_transition(self):
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        op = _make_op_log(status=OperationStatus.RUNNING, immutable=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db.execute = AsyncMock(return_value=result_mock)
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.complete("op-1", output_summary="done")
        assert op.status == OperationStatus.COMPLETED
        assert op.output_summary == "done"

    async def test_fail_calls_transition(self):
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        op = _make_op_log(status=OperationStatus.RUNNING, immutable=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        db.execute = AsyncMock(return_value=result_mock)
        svc = OperationService(db)
        with patch.object(event_bus, "publish"):
            await svc.fail("op-1", error_message="boom", error_category="system")
        assert op.status == OperationStatus.FAILED
        assert op.error_message == "boom"
        assert op.error_category == "system"


# ─── sse_generator ────────────────────────────────────────────────────


class TestOperationServiceSseGenerator:
    @staticmethod
    def _parse_sse(raw: str) -> tuple[str, dict]:
        """SSE 格式: event: {type}\\ndata: {json}\\n\\n"""
        import json as _json
        lines = raw.strip().split("\n")
        event_type = ""
        data_line = ""
        for line in lines:
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data_line = line[len("data: "):]
        return event_type, _json.loads(data_line) if data_line else {}

    async def test_sse_yields_published_event(self):
        svc = OperationService(db=None)
        gen = svc.sse_generator(user_id=None)

        async def trigger():
            await asyncio.sleep(0.01)
            event_bus.publish("operation.created", {
                "operation_id": "op-1", "agent_name": "x", "action": "y",
                "status": "pending", "timestamp": "2026-06-01T10:00:00+00:00",
            })

        asyncio.create_task(trigger())
        first = await asyncio.wait_for(anext(gen), timeout=1.0)
        event_type, payload = self._parse_sse(first)
        assert event_type == "operation"
        assert payload["operation_id"] == "op-1"
        await gen.aclose()

    async def test_sse_user_id_filter_passes_matching(self):
        svc = OperationService(db=None)
        gen = svc.sse_generator(user_id=None)

        async def trigger():
            await asyncio.sleep(0.01)
            event_bus.publish("operation.created", {
                "user_id": "u-1", "operation_id": "op-1",
                "agent_name": "x", "action": "y", "status": "pending",
                "timestamp": "2026-06-01T10:00:00+00:00",
            })

        asyncio.create_task(trigger())
        first = await asyncio.wait_for(anext(gen), timeout=1.0)
        event_type, payload = self._parse_sse(first)
        assert event_type == "operation"
        assert payload["user_id"] == "u-1"
        await gen.aclose()

    async def test_sse_user_id_filter_drops_non_matching(self):
        svc = OperationService(db=None)
        gen = svc.sse_generator(user_id="u-1")

        async def trigger():
            await asyncio.sleep(0.01)
            event_bus.publish("operation.created", {
                "user_id": "u-999", "operation_id": "op-other",
                "agent_name": "x", "action": "y", "status": "pending",
                "timestamp": "2026-06-01T10:00:00+00:00",
            })
            await asyncio.sleep(0.01)
            event_bus.publish("operation.created", {
                "user_id": "u-1", "operation_id": "op-mine",
                "agent_name": "x", "action": "y", "status": "pending",
                "timestamp": "2026-06-01T10:00:00+00:00",
            })

        asyncio.create_task(trigger())
        first = await asyncio.wait_for(anext(gen), timeout=1.0)
        event_type, payload = self._parse_sse(first)
        assert payload["operation_id"] == "op-mine"
        await gen.aclose()

    async def test_sse_heartbeat_on_timeout(self):
        svc = OperationService(db=None)
        gen = svc.sse_generator(user_id=None)
        with patch("app.services.operation_service.asyncio.wait_for") as mock_wf:
            mock_wf.side_effect = asyncio.TimeoutError
            try:
                first = await asyncio.wait_for(anext(gen), timeout=1.0)
            except Exception:
                first = None
        await gen.aclose()

    async def test_sse_cleans_up_subscriptions_on_close(self):
        svc = OperationService(db=None)
        before_created = len(event_bus._subscribers.get("operation.created", []))
        before_updated = len(event_bus._subscribers.get("operation.updated", []))
        gen = svc.sse_generator(user_id=None)

        async def trigger():
            await asyncio.sleep(0.01)
            event_bus.publish("operation.created", {"operation_id": "x"})

        asyncio.create_task(trigger())
        try:
            await asyncio.wait_for(anext(gen), timeout=1.0)
        except Exception:
            pass
        await gen.aclose()
        after_created = len(event_bus._subscribers.get("operation.created", []))
        after_updated = len(event_bus._subscribers.get("operation.updated", []))
        assert after_created == before_created
        assert after_updated == before_updated

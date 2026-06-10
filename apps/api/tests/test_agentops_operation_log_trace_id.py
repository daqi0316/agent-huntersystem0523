"""P1-3: OperationLog ↔ trace_id 关联测试。

验证点：
  1. OperationService.create() 在有 AgentOpsContext 时自动绑定 trace_id
  2. OperationService.create() 无 AgentOpsContext 时 trace_id 为空
  3. 显式传入 trace_id 优先于 context
  4. trace_id 写入后可通过 API 读取
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agentops.core.context import AgentOpsContext, reset_context, set_context
from app.models.operation_log import OperationStatus

pytestmark = pytest.mark.asyncio


# ── Helper: fake Service with mocked db ──


def _make_service():
    """Create OperationService with a mock db session."""
    from app.services.operation_service import OperationService

    svc = OperationService()
    svc.db = AsyncMock()
    return svc


async def _clean_context():
    """Ensure clean context between tests."""
    token = set_context(None)
    reset_context(token)


async def test_create_binds_trace_id_from_context() -> None:
    """AgentOpsContext 活跃时，create 自动绑定 trace_id。"""
    svc = _make_service()
    svc.db.add = MagicMock()
    svc.db.commit = AsyncMock()
    svc.db.refresh = AsyncMock()

    ctx = AgentOpsContext(trace_id="trace-001", user_id="user-1", session_id="session-1")
    token = set_context(ctx)
    try:
        op = await svc.create(
            user_id="user-1",
            agent_name="test_agent",
            action="test_action",
        )
        assert op.trace_id == "trace-001"
    finally:
        reset_context(token)


async def test_create_empty_trace_id_without_context() -> None:
    """无 AgentOpsContext 时，trace_id 为空。"""
    await _clean_context()
    svc = _make_service()
    svc.db.add = MagicMock()
    svc.db.commit = AsyncMock()
    svc.db.refresh = AsyncMock()

    op = await svc.create(
        user_id="user-1",
        agent_name="test_agent",
        action="test_action",
    )
    assert op.trace_id is None


async def test_create_explicit_trace_id_overrides_context() -> None:
    """显式传入的 trace_id 优先于 AgentOpsContext。"""
    svc = _make_service()
    svc.db.add = MagicMock()
    svc.db.commit = AsyncMock()
    svc.db.refresh = AsyncMock()

    ctx = AgentOpsContext(trace_id="ctx-trace", user_id="user-1")
    token = set_context(ctx)
    try:
        op = await svc.create(
            user_id="user-1",
            agent_name="test_agent",
            action="test_action",
            trace_id="explicit-trace",
        )
        assert op.trace_id == "explicit-trace"
        assert op.trace_id != "ctx-trace"
    finally:
        reset_context(token)


async def test_create_operation_api_exposes_trace_id() -> None:
    """POST /operations 返回的 data 包含 trace_id 字段。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.operations import router
    from app.core.database import get_db
    from app.core.dependencies import get_current_user_id

    mock_op = MagicMock()
    mock_op.id = "op-trace-test"
    mock_op.agent_name = "test_agent"
    mock_op.action = "test_action"
    mock_op.status = OperationStatus.COMPLETED
    mock_op.trace_id = "trace-42"
    mock_op.input_summary = ""
    mock_op.output_summary = ""
    mock_op.error_message = None
    mock_op.duration_ms = 100.0
    mock_op.created_at.isoformat.return_value = "2026-06-10T10:00:00"
    mock_op.updated_at.isoformat.return_value = "2026-06-10T10:00:01"

    test_app = FastAPI()
    test_app.include_router(router, prefix="/operations")
    test_app.dependency_overrides[get_current_user_id] = lambda: "test-user"
    test_app.dependency_overrides[get_db] = lambda: AsyncMock()

    mock_svc = AsyncMock()
    mock_svc.create = AsyncMock(return_value=mock_op)
    mock_svc.transition = AsyncMock()

    with patch("app.api.operations.OperationService", return_value=mock_svc), TestClient(test_app) as client:
        resp = client.post("/operations", params={
            "action": "test_action",
            "agent_name": "test_agent",
            "status": "completed",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 关键断言：trace_id 出现在 API 响应中
        assert data.get("trace_id") == "trace-42"


async def test_list_operations_exposes_trace_id() -> None:
    """GET /operations 列表中包含 trace_id。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.operations import router
    from app.core.database import get_db
    from app.core.dependencies import get_current_user_id

    mock_op = MagicMock()
    mock_op.id = "op-list-trace"
    mock_op.agent_name = "test_agent"
    mock_op.action = "test_action"
    mock_op.status = OperationStatus.COMPLETED
    mock_op.trace_id = "trace-list-99"
    mock_op.input_summary = ""
    mock_op.output_summary = ""
    mock_op.error_message = None
    mock_op.duration_ms = 50.0
    mock_op.created_at.isoformat.return_value = "2026-06-10T10:00:00"
    mock_op.updated_at.isoformat.return_value = "2026-06-10T10:00:01"

    test_app = FastAPI()
    test_app.include_router(router, prefix="/operations")
    test_app.dependency_overrides[get_current_user_id] = lambda: "test-user"
    test_app.dependency_overrides[get_db] = lambda: AsyncMock()

    mock_svc = AsyncMock()
    mock_svc.list = AsyncMock(return_value=([mock_op], 1))

    with patch("app.api.operations.OperationService", return_value=mock_svc), TestClient(test_app) as client:
        resp = client.get("/operations")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0].get("trace_id") == "trace-list-99"

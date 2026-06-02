"""Tests for app/agents/human_loop.py — Human-in-Loop approval agent.

覆盖 create_proposal / confirm / run / _generate_* / _execute_schedule_actions
以及 pending/history/status 查询 + Redis 索引写入 + 紧急停止。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.human_loop import (
    INTERVIEW_SCHEDULE_PROMPT,
    HumanLoopAgent,
)
from app.models.approval import ApprovalStatus


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def agent(mock_session: AsyncMock) -> HumanLoopAgent:
    a = HumanLoopAgent()
    return a


def _make_approval(
    id: str = "appr-1",
    action_type: str = "schedule_interview",
    proposal: dict | None = None,
    params: dict | None = None,
    status: ApprovalStatus = ApprovalStatus.PENDING,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    user_id: str = "user-1",
) -> MagicMock:
    a = MagicMock()
    a.id = id
    a.action_type = action_type
    a.proposal = proposal or {"recommended_slot": "2026-06-10T10:00:00", "duration_minutes": 60}
    a.params = params or {"candidate_email": "a@b.com", "candidate_name": "Alice", "job_title": "Engineer"}
    a.status = status
    a.user_id = user_id
    a.created_at = created_at or datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)
    a.expires_at = expires_at or datetime(2026, 6, 9, 12, 0, 0, tzinfo=UTC)
    return a


# ─── __init__ / llm property ──────────────────────────────────────────


class TestInit:
    def test_default_name(self) -> None:
        a = HumanLoopAgent()
        assert a.name == "human_loop"

    def test_custom_name(self) -> None:
        a = HumanLoopAgent(name="custom_loop")
        assert a.name == "custom_loop"

    def test_llm_lazy_init(self, agent: HumanLoopAgent) -> None:
        """首次访问 llm → 调用 get_llm_client, 之后复用."""
        fake_llm = MagicMock()
        with patch("app.agents.human_loop.get_llm_client", return_value=fake_llm) as mock_get:
            llm1 = agent.llm
            llm2 = agent.llm

        assert llm1 is fake_llm
        assert llm2 is fake_llm
        # 多次访问只调用一次
        assert mock_get.call_count == 1


# ─── _with_db ─────────────────────────────────────────────────────────


class TestWithDb:
    async def test_returns_service_and_session(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch("app.agents.human_loop.AsyncSessionLocal", return_value=mock_session):
            svc, sess = await agent._with_db()

        assert sess is mock_session
        assert svc is not None  # ApprovalService instance


# ─── create_proposal ──────────────────────────────────────────────────


class TestCreateProposal:
    async def test_success(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        gen_proposal = {"recommended_slot": "2026-06-15T10:00:00", "duration_minutes": 45}
        approval = _make_approval(
            id="new-1",
            action_type="schedule_interview",
            proposal=gen_proposal,
        )
        params = {"candidate_email": "x@y.com", "candidate_name": "Bob"}

        with patch("app.agents.human_loop.AsyncSessionLocal", return_value=mock_session), \
             patch.object(agent, "_generate_proposal", AsyncMock(return_value=gen_proposal)), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.create = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            result = await agent.create_proposal(
                user_id="user-1", action_type="schedule_interview", params=params
            )

        assert result["approval_id"] == "new-1"
        assert result["action_type"] == "schedule_interview"
        assert result["status"] == "pending"
        # result["proposal"] 来自 approval.proposal(持久化后的值)
        assert result["proposal"] == gen_proposal  # 来自 approval.proposal
        assert result["params"] == params
        assert "created_at" in result
        assert "expires_at" in result
        # session 一定被关闭
        mock_session.close.assert_awaited_once()

    async def test_email_fallback_to_email_key(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        """params.email 优先于 params.candidate_email."""
        approval = _make_approval(action_type="send_email")
        params = {"email": "alt@y.com", "candidate_name": "X"}

        with patch.object(agent, "_generate_proposal", AsyncMock(return_value={})), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.create = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            await agent.create_proposal(
                user_id="u", action_type="send_email", params=params
            )

        call = mock_svc.create.call_args
        assert call.kwargs["candidate_email"] == "alt@y.com"

    async def test_empty_email_passes_empty_string(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval = _make_approval()
        with patch.object(agent, "_generate_proposal", AsyncMock(return_value={})), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.create = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            await agent.create_proposal(
                user_id="u", action_type="x", params={"target_type": "job", "target_id": "j1"}
            )

        call = mock_svc.create.call_args
        assert call.kwargs["target_type"] == "job"
        assert call.kwargs["target_id"] == "j1"
        assert call.kwargs["candidate_email"] == ""

    async def test_thread_id_indexes_to_redis(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        """thread_id 非空 → 写入 Redis 索引."""
        approval = _make_approval(id="a1")
        fake_redis = AsyncMock()

        with patch.object(agent, "_generate_proposal", AsyncMock(return_value={})), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc, \
             patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            mock_svc = AsyncMock()
            mock_svc.create = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            await agent.create_proposal(
                user_id="u", action_type="x", params={}, thread_id="t-42"
            )

        fake_redis.set.assert_awaited_once()
        call = fake_redis.set.call_args
        assert call.args[0] == "appr:graph_thread:a1"
        assert call.args[1] == "t-42"
        assert call.kwargs["ex"] == 86400

    async def test_no_thread_id_skips_redis(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval = _make_approval()
        with patch.object(agent, "_generate_proposal", AsyncMock(return_value={})), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc, \
             patch("app.core.redis.get_redis", AsyncMock()) as mock_get_redis:
            mock_svc = AsyncMock()
            mock_svc.create = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            await agent.create_proposal(
                user_id="u", action_type="x", params={}  # no thread_id
            )

        mock_get_redis.assert_not_called()


# ─── _index_approval_to_thread (static) ───────────────────────────────


class TestIndexApprovalToThread:
    async def test_writes_to_redis(self) -> None:
        fake_redis = AsyncMock()
        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            await HumanLoopAgent._index_approval_to_thread("a1", "t1")

        fake_redis.set.assert_awaited_once_with(
            "appr:graph_thread:a1", "t1", ex=86400
        )

    async def test_redis_unavailable_warns_and_returns(self) -> None:
        """get_redis 抛异常 → 记录 warning, 不抛."""
        with patch("app.core.redis.get_redis", AsyncMock(side_effect=RuntimeError("Redis down"))):
            # 不应抛异常
            await HumanLoopAgent._index_approval_to_thread("a1", "t1")

    async def test_redis_returns_none(self) -> None:
        """get_redis 返回 None → 直接返回, 不调用 set."""
        with patch("app.core.redis.get_redis", AsyncMock(return_value=None)):
            await HumanLoopAgent._index_approval_to_thread("a1", "t1")

    async def test_redis_set_fails_warns(self) -> None:
        """set 抛异常 → 记录 warning, 不抛."""
        fake_redis = AsyncMock()
        fake_redis.set = AsyncMock(side_effect=RuntimeError("SET failed"))
        with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
            await HumanLoopAgent._index_approval_to_thread("a1", "t1")


# ─── confirm ──────────────────────────────────────────────────────────


class TestConfirm:
    async def test_approval_not_found(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch("app.agents.human_loop.AsyncSessionLocal", return_value=mock_session), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.resolve = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc

            result = await agent.confirm("missing", "u1", approved=True)

        assert result == {"error": "approval_not_found", "approval_id": "missing"}
        mock_session.close.assert_awaited_once()

    async def test_reject_returns_approval(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval = _make_approval(id="a1", status=ApprovalStatus.REJECTED)
        with patch("app.agents.human_loop.AsyncSessionLocal", return_value=mock_session), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.resolve = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            result = await agent.confirm("a1", "u1", approved=False, feedback="改天")

        assert result["approval_id"] == "a1"
        assert result["status"] == "rejected"
        assert result["feedback"] == "改天"
        assert "execution" not in result

    async def test_approve_schedule_executes(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval = _make_approval(action_type="schedule_interview")
        with patch("app.agents.human_loop.ApprovalService") as MockSvc, \
             patch.object(agent, "_execute_schedule_actions", AsyncMock()) as mock_exec:
            mock_svc = AsyncMock()
            mock_svc.resolve = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            result = await agent.confirm("a1", "u1", approved=True, feedback="OK")

        assert result["status"] == "pending"
        mock_exec.assert_awaited_once()
        # record 包含 params/proposal/execution
        record = mock_exec.call_args.args[0]
        assert "params" in record
        assert "proposal" in record
        assert "execution" in record

    async def test_approve_non_schedule_no_execution(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        """批准非 schedule 类型 → 不执行."""
        approval = _make_approval(action_type="send_email")
        with patch("app.agents.human_loop.ApprovalService") as MockSvc, \
             patch.object(agent, "_execute_schedule_actions", AsyncMock()) as mock_exec:
            mock_svc = AsyncMock()
            mock_svc.resolve = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            result = await agent.confirm("a1", "u1", approved=True)

        assert "execution" not in result
        mock_exec.assert_not_called()


# ─── run (dispatcher) ─────────────────────────────────────────────────


class TestRun:
    async def test_confirm_path(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval = _make_approval(status=ApprovalStatus.APPROVED)
        with patch.object(agent, "confirm", AsyncMock(return_value={"ok": True})) as mock_confirm:
            result = await agent.run({
                "confirm": True,
                "approval_id": "a1",
                "user_id": "u1",
                "approved": True,
            })

        assert result == {"ok": True}
        mock_confirm.assert_awaited_once()

    async def test_create_proposal_path(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval_dict = {
            "approval_id": "a1",
            "action_type": "send_email",
            "status": "pending",
        }
        with patch.object(agent, "create_proposal", AsyncMock(return_value=approval_dict)):
            result = await agent.run({
                "action_type": "send_email",
                "params": {"to": "x@y.com"},
                "user_id": "u1",
            })

        assert result["agent"] == "human_loop"
        assert result["status"] == "awaiting_approval"
        assert result["approval"] == approval_dict

    async def test_uses_resolver_id_when_user_id_empty(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch.object(agent, "confirm", AsyncMock()) as mock_confirm:
            await agent.run({
                "confirm": True,
                "approval_id": "a1",
                "user_id": "",
                "resolver_id": "resolver-1",
                "approved": True,
            })

        # confirm 应被调用,user_id 来自 resolver_id
        call = mock_confirm.call_args
        assert call.args[1] == "resolver-1"


# ─── _generate_proposal (dispatcher) ──────────────────────────────────


class TestGenerateProposal:
    async def test_schedule_interview(self, agent: HumanLoopAgent) -> None:
        with patch.object(agent, "_generate_interview_proposal", AsyncMock(return_value={"x": 1})):
            result = await agent._generate_proposal("schedule_interview", {})

        assert result == {"x": 1}

    async def test_send_email(self, agent: HumanLoopAgent) -> None:
        params = {"to": "a@b.com", "subject": "hi", "body": "x"}
        result = await agent._generate_proposal("send_email", params)

        assert result == {"to": "a@b.com", "subject": "hi", "body": "x"}

    async def test_unknown_action(self, agent: HumanLoopAgent) -> None:
        result = await agent._generate_proposal("custom_action", {"a": 1})

        assert result == {"action": "custom_action", "params": {"a": 1}}


# ─── _generate_interview_proposal ─────────────────────────────────────


class TestGenerateInterviewProposal:
    async def test_parses_json(self, agent: HumanLoopAgent) -> None:
        llm_response = json.dumps({
            "recommended_slot": "2026-06-10T10:00:00",
            "alternatives": ["备选1"],
            "duration_minutes": 45,
            "interview_type": "技术面",
            "suggested_interviewers": ["Tom"],
            "invitation_draft": "邀请",
        })
        agent._llm = MagicMock(chat=AsyncMock(return_value=llm_response))

        result = await agent._generate_interview_proposal({
            "candidate_name": "Alice",
            "job_title": "Engineer",
            "available_slots": ["2026-06-10T10:00:00"],
        })

        assert result["recommended_slot"] == "2026-06-10T10:00:00"
        assert result["duration_minutes"] == 45
        assert result["interview_type"] == "技术面"

    async def test_parses_json_with_markdown_fence(self, agent: HumanLoopAgent) -> None:
        """LLM 返回 ```json ... ``` 包裹的响应."""
        inner = json.dumps({"recommended_slot": "x", "duration_minutes": 30})
        llm_response = f"```json\n{inner}\n```"
        agent._llm = MagicMock(chat=AsyncMock(return_value=llm_response))

        result = await agent._generate_interview_proposal({})

        assert result["recommended_slot"] == "x"
        assert result["duration_minutes"] == 30

    async def test_fallback_on_invalid_json(self, agent: HumanLoopAgent) -> None:
        agent._llm = MagicMock(chat=AsyncMock(return_value="not json at all"))

        result = await agent._generate_interview_proposal({})

        assert "raw" in result
        assert result["error"] == "parse_failed"

    async def test_fallback_on_no_json_in_response(self, agent: HumanLoopAgent) -> None:
        agent._llm = MagicMock(chat=AsyncMock(return_value="Sorry, I cannot help."))

        result = await agent._generate_interview_proposal({})

        # 没有 {...} 模式 → 用整个 result 作为 text, json.loads 也会失败
        assert result.get("error") == "parse_failed" or "raw" in result

    async def test_uses_defaults(self, agent: HumanLoopAgent) -> None:
        """params 缺字段 → 使用默认值."""
        captured_messages = []
        agent._llm = MagicMock(chat=AsyncMock(side_effect=lambda m, **kw: captured_messages.append(m) or '{"ok": true}'))

        await agent._generate_interview_proposal({})  # 空 params

        # 验证 prompt 包含默认值
        prompt_content = captured_messages[0][0]["content"]
        assert "候选人" in prompt_content  # 默认 candidate_name
        assert "职位" in prompt_content      # 默认 job_title
        assert "无可用时间段" in prompt_content  # 默认 available_slots


# ─── _execute_schedule_actions ────────────────────────────────────────


class TestExecuteScheduleActions:
    async def test_email_and_calendar_success(self, agent: HumanLoopAgent) -> None:
        record = {
            "params": {
                "candidate_email": "a@b.com",
                "candidate_name": "Alice",
                "job_title": "Engineer",
            },
            "proposal": {
                "recommended_slot": "2026-06-10T10:00:00",
                "duration_minutes": 60,
                "invitation_draft": "请您面试",
            },
        }
        mcp_results = iter([
            {"sent": True, "msg_id": "m1"},     # email
            {"booked": True, "event_id": "e1"},  # calendar
        ])

        async def fake_mcp(*args, **kwargs):
            return next(mcp_results)

        with patch("app.agents.human_loop.mcp_call_tool", side_effect=fake_mcp):
            await agent._execute_schedule_actions(record)

        log = record["execution"]["log"]
        assert len(log) == 2
        assert log[0]["tool"] == "email"
        assert log[0]["status"] == "sent"
        assert log[1]["tool"] == "calendar"
        assert log[1]["status"] == "booked"
        assert "completed_at" in record["execution"]

    async def test_email_failure_logged(self, agent: HumanLoopAgent) -> None:
        record = {
            "params": {"candidate_email": "a@b.com"},
            "proposal": {"recommended_slot": "x", "duration_minutes": 30},
        }

        async def fake_mcp(*args, **kwargs):
            raise RuntimeError("SMTP error")

        with patch("app.agents.human_loop.mcp_call_tool", side_effect=fake_mcp):
            await agent._execute_schedule_actions(record)

        log = record["execution"]["log"]
        assert log[0]["status"] == "failed"
        assert "SMTP error" in log[0]["error"]

    async def test_calendar_failure_logged(self, agent: HumanLoopAgent) -> None:
        record = {
            "params": {"candidate_email": "a@b.com"},
            "proposal": {"recommended_slot": "2026-06-10T10:00:00", "duration_minutes": 30},
        }
        mcp_results = iter([
            {"ok": True},                        # email 成功
            RuntimeError("Calendar API down"),   # calendar 失败
        ])

        async def fake_mcp(*args, **kwargs):
            r = next(mcp_results)
            if isinstance(r, Exception):
                raise r
            return r

        with patch("app.agents.human_loop.mcp_call_tool", side_effect=fake_mcp):
            await agent._execute_schedule_actions(record)

        log = record["execution"]["log"]
        assert log[0]["status"] == "sent"
        assert log[1]["status"] == "failed"
        assert "Calendar API down" in log[1]["error"]

    async def test_no_email_skips_mcp(self, agent: HumanLoopAgent) -> None:
        """candidate_email 为空 → 不调用 MCP."""
        record = {
            "params": {"candidate_email": ""},
            "proposal": {},
        }
        with patch("app.agents.human_loop.mcp_call_tool", AsyncMock()) as mock_mcp:
            await agent._execute_schedule_actions(record)

        mock_mcp.assert_not_called()
        assert record["execution"]["log"] == []

    async def test_calendar_skipped_without_slot(self, agent: HumanLoopAgent) -> None:
        """没有 recommended_slot → 只发 email 不 book calendar."""
        record = {
            "params": {"candidate_email": "a@b.com"},
            "proposal": {},  # no recommended_slot
        }
        with patch("app.agents.human_loop.mcp_call_tool", AsyncMock(return_value={"ok": True})) as mock_mcp:
            await agent._execute_schedule_actions(record)

        # 只调用一次(email)
        assert mock_mcp.await_count == 1
        log = record["execution"]["log"]
        assert len(log) == 1
        assert log[0]["tool"] == "email"

    async def test_non_datetime_slot_uses_now(self, agent: HumanLoopAgent) -> None:
        """slot 不是字符串 → 用 datetime.now(UTC) 作为 start_dt."""
        record = {
            "params": {"candidate_email": "a@b.com"},
            "proposal": {"recommended_slot": 12345, "duration_minutes": 30},  # 非字符串
        }
        mcp_results = iter([{"ok": True}, {"ok": True}])

        async def fake_mcp(*args, **kwargs):
            return next(mcp_results)

        with patch("app.agents.human_loop.mcp_call_tool", side_effect=fake_mcp):
            await agent._execute_schedule_actions(record)

        # 应正常完成不抛异常
        log = record["execution"]["log"]
        assert log[1]["status"] == "booked"

    async def test_invitation_fallback(self, agent: HumanLoopAgent) -> None:
        """invitation_draft 为空 → 使用默认 body."""
        record = {
            "params": {"candidate_email": "a@b.com", "candidate_name": "Bob", "job_title": "Dev"},
            "proposal": {"recommended_slot": "x"},  # no invitation_draft
        }
        captured_args = []

        async def fake_mcp(url, tool_name, arguments):
            captured_args.append((tool_name, arguments))
            return {"ok": True}

        with patch("app.agents.human_loop.mcp_call_tool", side_effect=fake_mcp):
            await agent._execute_schedule_actions(record)

        # email 调用的 body 应包含 fallback
        email_call = next(c for c in captured_args if c[0] == "send_email")
        body = email_call[1]["body"]
        assert "Bob" in body
        assert "Dev" in body


# ─── get_pending_count / get_pending_proposals / history / status ────


class TestPendingAndHistory:
    async def test_get_pending_count(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch("app.agents.human_loop.AsyncSessionLocal", return_value=mock_session), \
             patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.list_pending = AsyncMock(return_value=[1, 2, 3])
            MockSvc.return_value = mock_svc

            count = await agent.get_pending_count()

        assert count == 3
        mock_session.close.assert_awaited_once()

    async def test_get_pending_proposals(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        pending = [{"a": 1}, {"b": 2}]
        with patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.list_pending = AsyncMock(return_value=pending)
            MockSvc.return_value = mock_svc

            result = await agent.get_pending_proposals()

        assert result == pending

    async def test_get_approval_history_default_limit(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.list_history = AsyncMock(return_value=[])
            MockSvc.return_value = mock_svc

            await agent.get_approval_history()

        mock_svc.list_history.assert_awaited_once_with(limit=50)

    async def test_get_approval_history_custom_limit(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.list_history = AsyncMock(return_value=[])
            MockSvc.return_value = mock_svc

            await agent.get_approval_history(limit=200)

        mock_svc.list_history.assert_awaited_once_with(limit=200)

    async def test_get_approval_status_found(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        approval = _make_approval(id="a1", status=ApprovalStatus.APPROVED)
        with patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get = AsyncMock(return_value=approval)
            MockSvc.return_value = mock_svc

            result = await agent.get_approval_status("a1")

        assert result == {"approval_id": "a1", "status": "approved", "found_in": "db"}

    async def test_get_approval_status_not_found(self, agent: HumanLoopAgent, mock_session: AsyncMock) -> None:
        with patch("app.agents.human_loop.ApprovalService") as MockSvc:
            mock_svc = AsyncMock()
            mock_svc.get = AsyncMock(return_value=None)
            MockSvc.return_value = mock_svc

            result = await agent.get_approval_status("missing")

        assert result is None


# ─── INTERVIEW_SCHEDULE_PROMPT 验证 ──────────────────────────────────


class TestPromptTemplate:
    def test_format(self) -> None:
        formatted = INTERVIEW_SCHEDULE_PROMPT.format(
            candidate_name="Alice",
            job_title="Engineer",
            available_slots='["slot1"]',
        )
        assert "Alice" in formatted
        assert "Engineer" in formatted
        assert "slot1" in formatted
        assert "recommended_slot" in formatted
        assert "interview_type" in formatted


# ─── _pending_purge_all ────────────────────────────────────────────────


class TestPendingPurgeAll:
    async def test_runs_update_query(self, agent: HumanLoopAgent) -> None:
        """紧急停止 → 发出 UPDATE 语句."""
        db = AsyncMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=None)
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        with patch("app.agents.human_loop.AsyncSessionLocal", return_value=db):
            await agent._pending_purge_all()

        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

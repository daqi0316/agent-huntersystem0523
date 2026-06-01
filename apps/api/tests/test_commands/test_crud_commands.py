"""Tests for CRUD command handlers — V.4 真实实现.

验证 7 个 handler:
- /read       → select by id
- /list      → list with pagination
- /search    → ilike search
- /add       → insert new entity
- /write     → update fields
- /delete    → delete by id
- /batch     → bulk delete / close / archive
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.commands import (
    CommandCategory,
    CommandContext,
    CommandErrorCode,
    CommandExecutor,
    CommandRegistry,
    CommandAuditService,
    register_all,
)
from app.commands.handlers.crud import (
    handle_read,
    handle_list,
    handle_search,
    handle_add,
    handle_write,
    handle_delete,
    handle_batch,
    _get_model,
    _parse_kv_args,
    _row_to_dict,
)
from app.models.candidate import Candidate, CandidateStatus
from app.models.job_position import JobPosition, JobStatus
from app.models.application import Application, ApplicationStatus


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def mock_db() -> AsyncMock:
    from unittest.mock import MagicMock
    db = AsyncMock()
    db.add = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def executor(mock_db: AsyncMock) -> CommandExecutor:
    reg = CommandRegistry()
    register_all(reg)
    return CommandExecutor(
        registry=reg,
        audit=CommandAuditService(db=mock_db),
        redis=None,
    )


@pytest.fixture
def ctx(mock_db: AsyncMock) -> CommandContext:
    return CommandContext(
        user_id="user-crud",
        permissions=["L1_BASIC", "L2_CONFIRM", "L3_ELEVATED", "L4_ADMIN"],
        session_id="sess-crud",
        db=mock_db,
    )


@pytest.fixture
def ctx_no_db() -> CommandContext:
    return CommandContext(
        user_id="user-crud",
        permissions=["L1_BASIC"],
        session_id="sess-crud",
        db=None,
    )


# ----------------------------------------------------------------------
# /read
# ----------------------------------------------------------------------

class TestHandleRead:
    @pytest.mark.asyncio
    async def test_read_requires_entity_and_id(self, ctx: CommandContext) -> None:
        result = await handle_read([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

        result = await handle_read(["candidate"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_read_unknown_entity(self, ctx: CommandContext) -> None:
        result = await handle_read(["unknown", "some-id"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "未知实体" in result.message

    @pytest.mark.asyncio
    async def test_read_without_db(self, ctx_no_db: CommandContext) -> None:
        result = await handle_read(["candidate", "some-id"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_read_not_found(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        from sqlalchemy import select
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        result = await handle_read(["candidate", "does-not-exist"], {}, ctx)

        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_read_returns_candidate(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        mock_candidate = MagicMock(spec=Candidate)
        mock_candidate.id = "cand-123"
        mock_candidate.name = "张三"
        mock_candidate.email = "zhangsan@example.com"
        mock_candidate.status = CandidateStatus.ACTIVE
        mock_candidate.created_at = None
        mock_candidate.updated_at = None

        from unittest.mock import PropertyMock
        col_names = ["id", "name", "email", "status", "created_at", "updated_at"]
        mock_cols = []
        for n in col_names:
            col = MagicMock()
            type(col).name = PropertyMock(return_value=n)
            mock_cols.append(col)
        mock_candidate.__table__ = MagicMock(columns=mock_cols)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_candidate)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await handle_read(["candidate", "cand-123"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["id"] == "cand-123"
        assert result.data["data"]["name"] == "张三"


# ----------------------------------------------------------------------
# /list
# ----------------------------------------------------------------------

class TestHandleList:
    @pytest.mark.asyncio
    async def test_list_requires_entity(self, ctx: CommandContext) -> None:
        result = await handle_list([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_list_unknown_entity(self, ctx: CommandContext) -> None:
        result = await handle_list(["unknown"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_list_without_db(self, ctx_no_db: CommandContext) -> None:
        result = await handle_list(["candidate"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_list_returns_paginated(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        from sqlalchemy import select, func
        from unittest.mock import PropertyMock

        col_names = ["id", "name", "created_at", "updated_at"]
        mock_candidates = []
        for i in range(3):
            mc = MagicMock(id=f"c{i}", name=f"User {i}", created_at=None, updated_at=None)
            mock_cols = []
            for n in col_names:
                col = MagicMock()
                type(col).name = PropertyMock(return_value=n)
                mock_cols.append(col)
            mc.__table__ = MagicMock(columns=mock_cols)
            mock_candidates.append(mc)

        count_result = MagicMock(scalar=MagicMock(return_value=10))
        list_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_candidates))))

        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        result = await handle_list(["candidate"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["total"] == 10
        assert len(result.data["items"]) == 3
        assert result.data["entity"] == "candidate"

    @pytest.mark.asyncio
    async def test_list_parses_limit_offset(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        count_result = MagicMock(scalar=MagicMock(return_value=5))
        list_result = MagicMock(scalars=MagicMock(all=MagicMock(return_value=[])))
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        result = await handle_list(["candidate", "--limit", "5", "--offset", "10"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["limit"] == 5
        assert result.data["offset"] == 10


# ----------------------------------------------------------------------
# /search
# ----------------------------------------------------------------------

class TestHandleSearch:
    @pytest.mark.asyncio
    async def test_search_requires_entity_and_keyword(self, ctx: CommandContext) -> None:
        result = await handle_search(["candidate"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_search_without_db(self, ctx_no_db: CommandContext) -> None:
        result = await handle_search(["candidate", "张三"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_search_returns_matches(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        from unittest.mock import PropertyMock
        col_names = ["id", "name", "created_at", "updated_at"]
        mock_candidates = []
        for name in ["张三", "张四"]:
            mc = MagicMock(id=f"c-{name}", name=name, created_at=None, updated_at=None)
            mock_cols = []
            for n in col_names:
                col = MagicMock()
                type(col).name = PropertyMock(return_value=n)
                mock_cols.append(col)
            mc.__table__ = MagicMock(columns=mock_cols)
            mock_candidates.append(mc)
        mock_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_candidates))))
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await handle_search(["candidate", "张"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert len(result.data["items"]) == 2


# ----------------------------------------------------------------------
# /add
# ----------------------------------------------------------------------

class TestHandleAdd:
    @pytest.mark.asyncio
    async def test_add_requires_entity_and_fields(self, ctx: CommandContext) -> None:
        result = await handle_add([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

        result = await handle_add(["candidate"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_add_without_db(self, ctx_no_db: CommandContext) -> None:
        result = await handle_add(["candidate", "name=张三", "email=a@b.com"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_add_creates_candidate(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        mock_obj = MagicMock(spec=Candidate)
        mock_obj.id = "new-cand-456"
        mock_obj.name = "张三"
        mock_obj.email = "a@b.com"
        mock_obj.created_at = None
        mock_obj.updated_at = None
        mock_db.refresh = AsyncMock(side_effect=lambda m: setattr(m, "id", "new-cand-456"))

        with patch("app.commands.handlers.crud.Candidate") as MockCandidate:
            MockCandidate.return_value = mock_obj
            result = await handle_add(["candidate", "name=张三", "email=a@b.com"], {}, ctx)

            assert result.error_code == CommandErrorCode.SUCCESS
            assert "add" in result.data["handler"]
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()


# ----------------------------------------------------------------------
# /write
# ----------------------------------------------------------------------

class TestHandleWrite:
    @pytest.mark.asyncio
    async def test_write_requires_entity_id_fields(self, ctx: CommandContext) -> None:
        result = await handle_write([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

        result = await handle_write(["candidate", "id-1"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_write_not_found(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        mock_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await handle_write(["candidate", "not-found", "name=newname"], {}, ctx)

        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_write_updates_status(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        mock_obj = MagicMock(spec=Candidate)
        mock_obj.id = "cand-update"
        mock_obj.status = CandidateStatus.ACTIVE
        mock_obj.created_at = None
        mock_obj.updated_at = None

        mock_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_obj))
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await handle_write(["candidate", "cand-update", "status=archived"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert mock_obj.status == CandidateStatus.ARCHIVED


# ----------------------------------------------------------------------
# /delete
# ----------------------------------------------------------------------

class TestHandleDelete:
    @pytest.mark.asyncio
    async def test_delete_requires_entity_and_id(self, ctx: CommandContext) -> None:
        result = await handle_delete([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_delete_not_found(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        mock_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await handle_delete(["candidate", "not-found"], {}, ctx)

        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_delete_without_db(self, ctx_no_db: CommandContext) -> None:
        result = await handle_delete(["candidate", "some-id"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED


# ----------------------------------------------------------------------
# /batch
# ----------------------------------------------------------------------

class TestHandleBatch:
    @pytest.mark.asyncio
    async def test_batch_requires_action_entity_ids(self, ctx: CommandContext) -> None:
        result = await handle_batch([], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

        result = await handle_batch(["delete"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS

        result = await handle_batch(["invalid", "candidate", "id1"], {}, ctx)
        assert result.error_code == CommandErrorCode.INVALID_ARGS
        assert "支持的操作" in result.message

    @pytest.mark.asyncio
    async def test_batch_delete_without_db(self, ctx_no_db: CommandContext) -> None:
        result = await handle_batch(["delete", "candidate", "id1", "id2"], {}, ctx_no_db)
        assert result.error_code == CommandErrorCode.NOT_IMPLEMENTED

    @pytest.mark.asyncio
    async def test_batch_delete_bulk(self, ctx: CommandContext, mock_db: AsyncMock) -> None:
        mock_result = MagicMock(rowcount=2)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await handle_batch(["delete", "candidate", "id1", "id2"], {}, ctx)

        assert result.error_code == CommandErrorCode.SUCCESS
        assert result.data["affected"] == 2
        assert result.data["action"] == "delete"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

class TestHelpers:
    def test_parse_kv_args_basic(self) -> None:
        result = _parse_kv_args(["name=张三", "email=a@b.com"])
        assert result["name"] == "张三"
        assert result["email"] == "a@b.com"

    def test_parse_kv_args_null(self) -> None:
        result = _parse_kv_args(["name=null"])
        assert result["name"] is None

    def test_parse_kv_args_bool(self) -> None:
        result = _parse_kv_args(["active=true", "disabled=false"])
        assert result["active"] is True
        assert result["disabled"] is False

    def test_parse_kv_args_int(self) -> None:
        result = _parse_kv_args(["years=5"])
        assert result["years"] == 5

    def test_get_model(self) -> None:
        assert _get_model("candidate") is Candidate
        assert _get_model("candidates") is Candidate
        assert _get_model("jd") is JobPosition
        assert _get_model("job") is JobPosition
        assert _get_model("application") is Application
        assert _get_model("unknown") is None

    def test_row_to_dict_enum(self) -> None:
        mock_row = MagicMock()
        mock_col = MagicMock()
        mock_col.name = "status"
        mock_row.__table__ = MagicMock()
        mock_row.__table__.columns = [mock_col]
        mock_row.status = CandidateStatus.ACTIVE

        result = _row_to_dict(mock_row)
        assert result["status"] == "active"


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------

class TestCrudRegistration:
    def test_all_7_commands_registered(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        crud_cmds = reg.list_by_category("crud")
        assert len(crud_cmds) == 7

    def test_list_alias(self) -> None:
        from app.commands import CommandRegistry, register_all
        reg = CommandRegistry()
        register_all(reg)
        resolved = reg.get("/l")
        assert resolved is not None
        assert resolved["name"] == "list"
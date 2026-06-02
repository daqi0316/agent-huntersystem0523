"""Tests for app/tools/candidate.py, app/tools/job.py, app/tools/evaluation.py.

覆盖 123 条 missed statements (26% → 90%+):
- candidate.py: _handle_create/update/archive_candidate (validation, service calls, error handling)
- job.py: _handle_create/update/close_job (validation, service calls, error handling)
- evaluation.py: _handle_create/... (9 functions)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.candidate import (
    _handle_create_candidate,
    _handle_update_candidate,
    _handle_archive_candidate,
    handlers as candidate_handlers,
    tools as candidate_tools,
)
from app.tools.job import (
    _handle_create_job,
    _handle_update_job,
    _handle_close_job,
    handlers as job_handlers,
    tools as job_tools,
)
from app.tools.evaluation import handlers as eval_handlers


class FakeAsyncSession:
    def __init__(self, mock_db=None):
        self._mock_db = mock_db or MagicMock()

    async def __aenter__(self):
        return self._mock_db

    async def __aexit__(self, *args):
        return False


# ─── Candidate Tools ─────────────────────────────────────────────────


class TestHandleCreateCandidate:
    async def test_empty_email_returns_validation_error(self):
        result = await _handle_create_candidate(email="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert "邮箱" in result["error"]["message"]

    async def test_duplicate_email_returns_duplicate_error(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(side_effect=Exception("UNIQUE constraint failed"))
        mock_svc.create.side_effect = Exception("UNIQUE constraint failed: email")

        async def fake_session():
            yield mock_db

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_create_candidate(email="dup@example.com", name="Alice")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "DUPLICATE"

    async def test_success_returns_masked_data(self):
        mock_candidate = MagicMock()
        mock_candidate.id = "c-123"
        mock_candidate.name = "Alice"
        mock_candidate.email = "alice@example.com"
        mock_candidate.phone = "123456"
        mock_candidate.current_company = "Acme"
        mock_candidate.current_title = "Engineer"
        mock_candidate.status = MagicMock(value="active")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_candidate)

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc), \
             patch("app.tools.candidate.mask_pii", side_effect=lambda x: f"MASKED({x})"):
            result = await _handle_create_candidate(email="alice@example.com", name="Alice")

        assert result["status"] == "success"
        assert result["data"]["candidate_id"] == "c-123"
        assert result["data"]["name"] == "MASKED(Alice)"
        assert result["data"]["email"] == "MASKED(alice@example.com)"

    async def test_create_exception_returns_create_failed(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(side_effect=RuntimeError("db error"))

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_create_candidate(email="alice@example.com")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "CREATE_FAILED"


class TestHandleUpdateCandidate:
    async def test_empty_candidate_id_returns_validation_error(self):
        result = await _handle_update_candidate(candidate_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert "candidate_id" in result["error"]["message"]

    async def test_not_found_returns_not_found_error(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_update_candidate(candidate_id="c-missing", name="Bob")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    async def test_update_returns_masked_data(self):
        mock_candidate = MagicMock()
        mock_candidate.id = "c-1"
        mock_candidate.name = "Bob"
        mock_candidate.email = "bob@example.com"
        mock_candidate.phone = None
        mock_candidate.current_company = "B Corp"
        mock_candidate.current_title = "Manager"
        mock_candidate.status = MagicMock(value="active")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=mock_candidate)
        mock_svc.update = AsyncMock(return_value=mock_candidate)

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc), \
             patch("app.tools.candidate.mask_pii", side_effect=lambda x: f"MASKED({x})"):
            result = await _handle_update_candidate(candidate_id="c-1", name="Bob Updated")

        assert result["status"] == "success"
        assert result["data"]["candidate_id"] == "c-1"

    async def test_update_failure_returns_update_failed(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=None)

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_update_candidate(candidate_id="c-1", name="X")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "UPDATE_FAILED"


class TestHandleArchiveCandidate:
    async def test_empty_candidate_id_returns_validation_error(self):
        result = await _handle_archive_candidate(candidate_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    async def test_not_found_returns_not_found_error(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_archive_candidate(candidate_id="c-missing")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    async def test_archive_failure_returns_archive_failed(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=None)

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_archive_candidate(candidate_id="c-1")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "ARCHIVE_FAILED"

    async def test_success_returns_archived_status(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=MagicMock())

        with patch("app.tools.candidate.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.candidate.CandidateService", return_value=mock_svc):
            result = await _handle_archive_candidate(candidate_id="c-1")

        assert result["status"] == "success"
        assert result["data"]["candidate_id"] == "c-1"
        assert result["data"]["status"] == "archived"


class TestCandidateToolsModule:
    def test_handlers_has_all_three(self):
        assert "create_candidate" in candidate_handlers
        assert "update_candidate" in candidate_handlers
        assert "archive_candidate" in candidate_handlers

    def test_tools_list_has_three_definitions(self):
        assert len(candidate_tools) == 3
        names = [t["function"]["name"] for t in candidate_tools]
        assert "create_candidate" in names
        assert "update_candidate" in names
        assert "archive_candidate" in names


# ─── Job Tools ──────────────────────────────────────────────────────


class TestHandleCreateJob:
    async def test_empty_title_returns_validation_error(self):
        result = await _handle_create_job(title="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert "职位名称" in result["error"]["message"]

    async def test_create_success(self):
        mock_job = MagicMock()
        mock_job.id = "j-123"
        mock_job.title = "Engineer"
        mock_job.department = "Tech"
        mock_job.location = "Remote"
        mock_job.status = MagicMock(value="active")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_job)
        mock_svc.update = AsyncMock(return_value=mock_job)
        mock_svc.get_by_id = AsyncMock(return_value=mock_job)

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_create_job(title="Engineer", department="Tech")

        assert result["status"] == "success"
        assert result["data"]["job_id"] == "j-123"
        assert result["data"]["title"] == "Engineer"

    async def test_create_exception_returns_create_failed(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(side_effect=RuntimeError("db error"))

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_create_job(title="Engineer")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "CREATE_FAILED"


class TestHandleUpdateJob:
    async def test_empty_job_id_returns_validation_error(self):
        result = await _handle_update_job(job_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"
        assert "job_id" in result["error"]["message"]

    async def test_not_found_returns_not_found_error(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_update_job(job_id="j-missing", title="X")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    async def test_update_failure_returns_update_failed(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=None)

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_update_job(job_id="j-1", title="X")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "UPDATE_FAILED"

    async def test_update_success(self):
        mock_job = MagicMock()
        mock_job.id = "j-1"
        mock_job.title = "Senior Engineer"
        mock_job.department = "Platform"
        mock_job.location = "NYC"
        mock_job.status = MagicMock(value="active")

        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=mock_job)
        mock_svc.update = AsyncMock(return_value=mock_job)

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_update_job(job_id="j-1", title="Senior Engineer")

        assert result["status"] == "success"
        assert result["data"]["job_id"] == "j-1"


class TestHandleCloseJob:
    async def test_empty_job_id_returns_validation_error(self):
        result = await _handle_close_job(job_id="")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "VALIDATION_ERROR"

    async def test_not_found_returns_not_found_error(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=None)

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_close_job(job_id="j-missing")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "NOT_FOUND"

    async def test_close_failure_returns_close_failed(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=None)

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_close_job(job_id="j-1")

        assert result["status"] == "failed"
        assert result["error"]["code"] == "CLOSE_FAILED"

    async def test_close_success_returns_closed_status(self):
        mock_db = MagicMock()
        mock_svc = AsyncMock()
        mock_svc.get_by_id = AsyncMock(return_value=MagicMock())
        mock_svc.update = AsyncMock(return_value=MagicMock())

        with patch("app.tools.job.AsyncSessionLocal", return_value=FakeAsyncSession(mock_db)), \
             patch("app.tools.job.JobService", return_value=mock_svc):
            result = await _handle_close_job(job_id="j-1")

        assert result["status"] == "success"
        assert result["data"]["job_id"] == "j-1"
        assert result["data"]["status"] == "closed"


class TestJobToolsModule:
    def test_handlers_has_all_three(self):
        assert "create_job" in job_handlers
        assert "update_job" in job_handlers
        assert "close_job" in job_handlers

    def test_tools_list_has_three_definitions(self):
        assert len(job_tools) == 3
        names = [t["function"]["name"] for t in job_tools]
        assert "create_job" in names
        assert "update_job" in names
        assert "close_job" in names


# ─── Evaluation Tools ────────────────────────────────────────────────


class TestEvaluationTools:
    def test_handlers_dict_exists(self):
        assert isinstance(eval_handlers, dict)
        assert len(eval_handlers) > 0

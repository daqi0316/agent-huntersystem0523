from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from app.services.application import ApplicationService


class TestList:
    async def test_with_related_objects(self):
        mock_db = AsyncMock()
        mr = Mock()
        mock_db.execute.return_value = mr

        app = Mock()
        app.id = "app-1"
        app.candidate_id = "cand-1"
        app.job_id = "job-1"
        app.status = "active"
        app.match_score = 0.85
        app.ai_summary = "good"
        app.resume_url = None
        app.created_at = "2024-01-01"
        app.updated_at = "2024-01-02"

        candidate = Mock()
        candidate.name = "Test Candidate"
        app.candidate = candidate

        job = Mock()
        job.title = "Engineer"
        app.job = job

        mr.scalars.return_value.all.return_value = [app]

        # Mock the scalar for count
        count_mr = Mock()
        count_mr.scalar.return_value = 1
        # We need two separate execute calls: count then list
        mock_db.execute.side_effect = [count_mr, mr]

        svc = ApplicationService(mock_db)
        items, total = await svc.list()

        assert len(items) == 1
        assert items[0]["id"] == "app-1"
        assert items[0]["candidate_name"] == "Test Candidate"
        assert items[0]["job_title"] == "Engineer"
        assert total == 1

    async def test_with_enum_status(self):
        mock_db = AsyncMock()
        mr = Mock()
        mock_db.execute.return_value = mr

        app = Mock()
        app.id = "app-2"
        app.candidate_id = "cand-2"
        app.job_id = "job-2"
        app.status = Mock()
        app.status.value = "evaluating"  # enum with .value
        app.match_score = 0.75
        app.ai_summary = None
        app.resume_url = "resume.pdf"
        app.created_at = "2024-02-01"
        app.updated_at = "2024-02-02"

        app.candidate = None
        app.job = None

        mr.scalars.return_value.all.return_value = [app]
        count_mr = Mock()
        count_mr.scalar.return_value = 1
        mock_db.execute.side_effect = [count_mr, mr]

        svc = ApplicationService(mock_db)
        items, total = await svc.list()

        assert len(items) == 1
        # Should have converted status via .value
        assert items[0]["status"] == "evaluating"
        assert items[0]["candidate_name"] == ""
        assert items[0]["job_title"] == ""

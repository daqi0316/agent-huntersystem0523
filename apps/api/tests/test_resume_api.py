"""Tests for resume API — upload, extract, confirm routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.schemas.resume import ExtractedCandidate


@pytest.fixture
def app():
    _app = FastAPI()
    from app.api.resume import router
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestUploadResume:
    def test_unsupported_extension(self, client):
        resp = client.post("/upload-resume", files={"file": ("resume.exe", b"data", "application/octet-stream")})
        assert resp.status_code == 400
        assert "不支持的文件格式" in resp.json()["detail"]

    def test_empty_filename_returns_422(self, client):
        resp = client.post("/upload-resume", files={"file": ("", b"data", "text/plain")})
        assert resp.status_code == 422

    def test_empty_file(self, client):
        resp = client.post("/upload-resume", files={"file": ("resume.txt", b"", "text/plain")})
        assert resp.status_code == 400
        assert "文件为空" in resp.json()["detail"]

    def test_parse_error(self, client):
        with patch("app.api.resume.parse_resume") as mock_parse:
            from app.services.resume_parser import ResumeParseError
            mock_parse.side_effect = ResumeParseError("解析失败")
            resp = client.post("/upload-resume", files={"file": ("resume.txt", b"content", "text/plain")})
        assert resp.status_code == 422

    def test_success_txt(self, client):
        with patch("app.api.resume.parse_resume", return_value="Hello World"):
            resp = client.post("/upload-resume", files={"file": ("resume.txt", b"Hello World", "text/plain")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["text_length"] == 11
        assert data["plain_text"] == "Hello World"
        assert data["filename"] == "resume.txt"

    def test_file_too_large(self, client):
        big_data = b"x" * (10 * 1024 * 1024 + 1)
        resp = client.post("/upload-resume", files={"file": ("resume.txt", big_data, "text/plain")})
        assert resp.status_code == 400
        assert "文件过大" in resp.json()["detail"]


class TestExtractResume:
    def test_success(self, client):
        candidate = ExtractedCandidate(
            name="张三", email="zhang@test.com", phone="13800138000",
            skills=["Python"], experience_years=5, raw_text="张三简历",
        )

        with (
            patch("app.api.resume.parse_resume", return_value="张三简历"),
            patch("app.api.resume.extract_from_text") as mock_extract,
        ):
            mock_extract.return_value = candidate
            resp = client.post("/extract-resume", files={"file": ("resume.txt", "张三简历".encode(), "text/plain")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate"]["name"] == "张三"
        assert data["needs_review"] is False

    def test_extraction_fallback(self, client):
        with (
            patch("app.api.resume.parse_resume", return_value="some text"),
            patch("app.api.resume.extract_from_text") as mock_extract,
        ):
            mock_extract.side_effect = Exception("LLM failed")
            resp = client.post("/extract-resume", files={"file": ("resume.txt", b"some text", "text/plain")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_review"] is True
        assert data["candidate"]["raw_text"] == "some text"

    def test_empty_filename_returns_422(self, client):
        resp = client.post("/extract-resume", files={"file": ("", b"data", "text/plain")})
        assert resp.status_code == 422

    def test_parse_error(self, client):
        with patch("app.api.resume.parse_resume") as mock_parse:
            from app.services.resume_parser import ResumeParseError
            mock_parse.side_effect = ResumeParseError("解析失败")
            resp = client.post("/extract-resume", files={"file": ("resume.txt", b"content", "text/plain")})
        assert resp.status_code == 422

    def test_file_too_large(self, client):
        big_data = b"x" * (10 * 1024 * 1024 + 1)
        resp = client.post("/extract-resume", files={"file": ("resume.txt", big_data, "text/plain")})
        assert resp.status_code == 400
        assert "文件过大" in resp.json()["detail"]


class TestConfirmResume:
    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def override_get_db(self, app, mock_db_session):
        from app.core.database import get_db

        async def _mock_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = _mock_get_db
        yield
        app.dependency_overrides.pop(get_db, None)

    def test_missing_email(self, client, override_get_db):
        resp = client.post("/confirm-resume", json={
            "parsed": {
                "name": "Test",
                "email": "",
                "phone": "",
                "skills": [],
                "experience_years": None,
            },
        })
        assert resp.status_code == 422
        assert "邮箱不能为空" in resp.json()["detail"]

    def test_success(self, client, override_get_db, mock_db_session):
        mock_candidate = MagicMock()
        mock_candidate.id = "cand-123"
        mock_candidate.name = "Test User"

        with patch("app.api.resume.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.create.return_value = mock_candidate
            MockSvc.return_value = svc
            resp = client.post("/confirm-resume", json={
                "parsed": {
                    "name": "Test User",
                    "email": "test@example.com",
                    "phone": "13800138000",
                    "summary": "A developer",
                    "skills": ["Python"],
                    "experience_years": 5,
                    "education": "本科",
                    "current_company": "Acme",
                    "current_title": "Engineer",
                    "raw_text": "resume text",
                },
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate_id"] == "cand-123"
        assert data["candidate_name"] == "Test User"

    def test_duplicate_email(self, client, override_get_db, mock_db_session):
        with patch("app.api.resume.CandidateService") as MockSvc:
            svc = AsyncMock()
            svc.create.side_effect = Exception("duplicate key value violates unique constraint")
            MockSvc.return_value = svc
            resp = client.post("/confirm-resume", json={
                "parsed": {
                    "name": "Dup", "email": "dup@test.com", "phone": "",
                    "skills": [], "experience_years": None,
                },
            })
        assert resp.status_code == 409
        assert "该邮箱已存在候选人" in resp.json()["detail"]

    def test_with_screening(self, client, override_get_db, mock_db_session):
        mock_candidate = MagicMock()
        mock_candidate.id = "cand-screen"
        mock_candidate.name = "Screen User"

        with (
            patch("app.api.resume.CandidateService") as MockSvc,
            patch("app.services.screening.ScreeningService") as MockScrSvc,
        ):
            svc = AsyncMock()
            svc.create.return_value = mock_candidate
            MockSvc.return_value = svc

            scr_svc = MagicMock()
            scr_svc.screen_resume = AsyncMock(return_value={"gate_passed": True})
            MockScrSvc.return_value = scr_svc

            resp = client.post("/confirm-resume", json={
                "parsed": {
                    "name": "Screen User",
                    "email": "screen@test.com",
                    "phone": "",
                    "skills": [],
                    "experience_years": None,
                    "raw_text": "resume text",
                },
                "run_screening": True,
                "job_id": "job-1",
            })
        assert resp.status_code == 200
        assert resp.json()["screening_result"] is not None

"""Tests for app/api/file_upload.py — temp file upload endpoint."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.file_upload import router as upload_router
from app.tools.file_parser import cleanup_temp_file


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(upload_router, prefix="/upload")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _make_upload(content: bytes, filename: str, content_type: str = "application/octet-stream"):
    """构造 multipart upload dict: {form_field: (filename, content, content_type)}."""
    return {"file": (filename, content, content_type)}


class TestUploadValidation:
    def test_unsupported_extension(self, client: TestClient) -> None:
        """不支持的扩展名 → 400."""
        resp = client.post("/upload/upload", files=_make_upload(b"data", "evil.exe"))
        assert resp.status_code == 400
        assert "不支持的文件格式" in resp.json()["error"]

    def test_supported_extensions(self, client: TestClient) -> None:
        """所有支持的扩展名 → 正常处理."""
        for ext in ["pdf", "docx", "doc", "txt", "jpg", "png"]:
            with patch("app.api.file_upload.save_temp_file", new=AsyncMock(return_value=f"/tmp/test.{ext}")):
                resp = client.post("/upload/upload", files=_make_upload(b"x", f"f.{ext}"))
                assert resp.status_code == 200, f"ext={ext} failed: {resp.text}"

    def test_no_extension(self, client: TestClient) -> None:
        """无扩展名 → 400 (因为空 ext 不在 SUPPORTED_TYPES)."""
        resp = client.post("/upload/upload", files=_make_upload(b"x", "noext"))
        assert resp.status_code == 400
        assert "不支持的文件格式" in resp.json()["error"]

    def test_uppercase_extension_lowered(self, client: TestClient) -> None:
        """大写扩展名被小写后接受."""
        with patch("app.api.file_upload.save_temp_file", new=AsyncMock(return_value="/tmp/upper.PDF")):
            resp = client.post("/upload/upload", files=_make_upload(b"x", "RESUME.PDF"))
            assert resp.status_code == 200


class TestUploadContentSize:
    """直接调用 endpoint 函数测试大小校验（绕过 multipart 框架层校验）."""

    def test_empty_content_returns_400(self) -> None:
        from app.api.file_upload import upload_file
        from fastapi import UploadFile
        import io
        import json
        import asyncio

        upload = UploadFile(filename="empty.pdf", file=io.BytesIO(b""))
        resp = asyncio.run(upload_file(upload))
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert "文件为空" in body["error"]

    def test_oversized_content_returns_400(self) -> None:
        from app.api.file_upload import upload_file, MAX_FILE_SIZE
        from fastapi import UploadFile
        import io
        import json
        import asyncio

        big = b"x" * (MAX_FILE_SIZE + 1)
        upload = UploadFile(filename="big.pdf", file=io.BytesIO(big))
        resp = asyncio.run(upload_file(upload))
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert "文件过大" in body["error"]

    def test_exactly_max_size_accepted(self) -> None:
        from app.api.file_upload import upload_file, MAX_FILE_SIZE
        from fastapi import UploadFile
        import io
        import asyncio
        from unittest.mock import patch

        exact = b"x" * MAX_FILE_SIZE
        upload = UploadFile(filename="edge.pdf", file=io.BytesIO(exact))
        with patch("app.api.file_upload.save_temp_file", new=AsyncMock(return_value="/tmp/edge.pdf")):
            result = asyncio.run(upload_file(upload))
        assert "file_url" in result
        assert result["file_size"] == MAX_FILE_SIZE


class TestUploadSuccess:
    def test_success(self, client: TestClient) -> None:
        """正常上传 → 返回 file_url/filename/file_size."""
        with patch("app.api.file_upload.save_temp_file", new=AsyncMock(return_value="/tmp/abc.pdf")):
            resp = client.post("/upload/upload", files=_make_upload(b"PDF content", "resume.pdf"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["file_url"] == "/tmp/abc.pdf"
        assert body["filename"] == "resume.pdf"
        assert body["file_size"] == 11

    def test_save_failure_returns_500(self, client: TestClient) -> None:
        """save_temp_file 抛异常 → 500."""
        from app.tools.file_parser import ResumeDownloadError

        with patch(
            "app.api.file_upload.save_temp_file",
            new=AsyncMock(side_effect=ResumeDownloadError("disk full")),
        ):
            resp = client.post("/upload/upload", files=_make_upload(b"x", "r.pdf"))
        assert resp.status_code == 500
        assert "文件保存失败" in resp.json()["error"]


class TestEndToEnd:
    def test_real_save_temp_file(self, client: TestClient) -> None:
        """不 mock save_temp_file，真实写入 tmpdir 并清理."""
        content = b"%PDF-1.4 real test content"
        resp = client.post("/upload/upload", files=_make_upload(content, "real.pdf"))
        assert resp.status_code == 200
        path = resp.json()["file_url"]
        try:
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == content
        finally:
            cleanup_temp_file(path)

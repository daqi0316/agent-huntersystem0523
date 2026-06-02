"""Tests for app/tools/file_parser.py — download + temp file management."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tools.file_parser import (
    ResumeDownloadError,
    cleanup_temp_file,
    download_and_save,
    download_file,
    file_exists,
    get_temp_file_path,
    save_temp_file,
)


class TestDownloadFile:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """正常下载成功."""
        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4 fake resume content"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await download_file("https://example.com/resume.pdf")
        assert result == b"%PDF-1.4 fake resume content"
        mock_client.get.assert_awaited_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_raises_download_error(self) -> None:
        """下载超时 → ResumeDownloadError."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ResumeDownloadError, match="下载超时"):
                await download_file("https://slow.example.com/r.pdf", timeout=1.0)

    @pytest.mark.asyncio
    async def test_http_status_error_raises(self) -> None:
        """HTTP 4xx/5xx → ResumeDownloadError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "not found", request=MagicMock(), response=mock_response
            )
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ResumeDownloadError, match="下载失败 \\(404\\)"):
                await download_file("https://example.com/missing.pdf")

    @pytest.mark.asyncio
    async def test_generic_exception_raises(self) -> None:
        """网络断开等通用异常 → ResumeDownloadError."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("network down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ResumeDownloadError, match="下载异常"):
                await download_file("https://unreachable.example.com/r.pdf")


class TestGetTempFilePath:
    def test_with_extension(self) -> None:
        """带扩展名的文件名保留后缀."""
        path = get_temp_file_path("resume.pdf")
        assert path.endswith(".pdf")
        assert tempfile.gettempdir() in path
        assert "resume_" in path

    def test_without_extension(self) -> None:
        """无扩展名 → 路径无后缀."""
        path = get_temp_file_path("resume")
        assert not path.endswith(".")
        assert "resume_" in path

    def test_empty_filename(self) -> None:
        """空文件名 → 无后缀."""
        path = get_temp_file_path("")
        assert "resume_" in path
        basename = os.path.basename(path)
        assert basename.startswith("resume_")
        assert "." not in basename

    def test_uppercase_extension_lowered(self) -> None:
        """大写扩展名 → 小写."""
        path = get_temp_file_path("RESUME.PDF")
        assert path.endswith(".pdf")

    def test_unique_paths(self) -> None:
        """连续生成应得到不同路径."""
        paths = {get_temp_file_path("r.pdf") for _ in range(10)}
        assert len(paths) == 10


class TestSaveTempFile:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """保存字节到临时文件成功."""
        content = b"hello world"
        path = await save_temp_file(content, "test.txt")
        try:
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == content
        finally:
            cleanup_temp_file(path)

    @pytest.mark.asyncio
    async def test_os_error_raises(self) -> None:
        """OS 错误 → ResumeDownloadError."""
        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(ResumeDownloadError, match="保存临时文件失败"):
                await save_temp_file(b"x", "x.txt")


class TestCleanupTempFile:
    def test_existing_file_deleted(self) -> None:
        """存在的文件被删除."""
        fd, path = tempfile.mkstemp()
        os.close(fd)
        assert os.path.exists(path)
        cleanup_temp_file(path)
        assert not os.path.exists(path)

    def test_nonexistent_file_no_error(self) -> None:
        """不存在的文件不报错."""
        cleanup_temp_file("/tmp/this_does_not_exist_xyz_12345")
        # 静默成功，无异常

    def test_none_path_no_error(self) -> None:
        """None 路径不报错."""
        cleanup_temp_file(None)  # type: ignore[arg-type]

    def test_empty_path_no_error(self) -> None:
        """空路径不报错."""
        cleanup_temp_file("")

    def test_oserror_during_remove_logged(self) -> None:
        """删除时 OSError 被记录但不抛出."""
        fd, path = tempfile.mkstemp()
        os.close(fd)
        with patch("os.remove", side_effect=OSError("permission denied")):
            cleanup_temp_file(path)
        # 文件可能仍在（OSError 被吞掉），但函数不抛异常
        if os.path.exists(path):
            os.remove(path)


class TestFileExists:
    def test_existing(self) -> None:
        """存在的文件 → True."""
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            assert file_exists(path) is True
        finally:
            os.remove(path)

    def test_nonexistent(self) -> None:
        """不存在的文件 → False."""
        assert file_exists("/tmp/nonexistent_xyz_99999") is False

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert file_exists(None) is False  # type: ignore[arg-type]

    def test_empty_string_returns_false(self) -> None:
        """空字符串 → False."""
        assert file_exists("") is False


class TestDownloadAndSave:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """下载并保存完整流程."""
        mock_response = MagicMock()
        mock_response.content = b"PDF content here"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            path = await download_and_save("https://example.com/r.pdf", "r.pdf")
        try:
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == b"PDF content here"
            assert path.endswith(".pdf")
        finally:
            cleanup_temp_file(path)

    @pytest.mark.asyncio
    async def test_download_failure_propagates(self) -> None:
        """下载失败时错误传播，不保存文件."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ResumeDownloadError):
                await download_and_save("https://slow.example.com/r.pdf", "r.pdf")

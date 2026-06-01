"""Tests for app.agents.prompts — file-based system prompt loader."""

import builtins
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.agents.prompts import load_prompt, reload_prompts, get_available_prompts


def _patch_prompt_dir(tmp_path) -> str:
    """Return a temp dir path and patch _PROMPT_DIR to point at it."""
    return str(tmp_path)


def test_load_prompt_returns_cached_value_on_second_call():
    """When the same prompt is loaded twice, the second call returns cached content without re-reading."""
    with patch("app.agents.prompts.os.path.exists", return_value=True):
        with patch("app.agents.prompts.open", mock_open(read_data="hello world")) as mock_file:
            content1 = load_prompt("test_prompt")
            assert content1 == "hello world"

            # Reset call count — second call should NOT open the file
            mock_file.reset_mock()
            content2 = load_prompt("test_prompt")
            assert content2 == "hello world"
            mock_file.assert_not_called()


def test_load_prompt_returns_empty_string_when_file_not_found():
    """load_prompt returns '' when the .md file doesn't exist."""
    with patch("app.agents.prompts.os.path.exists", return_value=False):
        with patch("app.agents.prompts.logger") as mock_logger:
            content = load_prompt("nonexistent")
            assert content == ""
            mock_logger.warning.assert_called_once()


def test_load_prompt_strips_content():
    """load_prompt strips leading/trailing whitespace from file content."""
    with patch("app.agents.prompts.os.path.exists", return_value=True):
        with patch("app.agents.prompts.open", mock_open(read_data="  hello world\n\n")):
            content = load_prompt("strip_test")
            assert content == "hello world"


def test_load_prompt_handles_read_error():
    """load_prompt returns '' and logs warning when file read fails."""
    with patch("app.agents.prompts.os.path.exists", return_value=True):
        with patch("app.agents.prompts.open", side_effect=OSError("permission denied")):
            with patch("app.agents.prompts.logger") as mock_logger:
                content = load_prompt("error_prompt")
                assert content == ""
                mock_logger.warning.assert_called_once()


def test_reload_prompts_clears_cache():
    """After reload_prompts(), the next load_prompt re-reads from disk."""
    with patch("app.agents.prompts.os.path.exists", return_value=True):
        with patch("app.agents.prompts.open", mock_open(read_data="cached content")) as mock_file:
            # First call populates cache
            assert load_prompt("cache_test") == "cached content"
            mock_file.reset_mock()

            # Reload clears cache
            with patch("app.agents.prompts.logger") as mock_logger:
                reload_prompts()
                mock_logger.info.assert_called_once()

            # Second call should re-open the file even though same content
            assert load_prompt("cache_test") == "cached content"
            mock_file.assert_called_once()


def test_get_available_prompts_lists_md_files():
    """get_available_prompts returns .md filenames without suffix, sorted."""
    with patch("app.agents.prompts.os.listdir") as mock_listdir:
        mock_listdir.return_value = ["z_last.md", "alpha.md", "beta.md", "not_md.txt", "readme"]
        result = get_available_prompts()
        assert result == ["alpha", "beta", "z_last"]


def test_get_available_prompts_returns_empty_when_no_md_files():
    """get_available_prompts returns empty list when no .md files exist."""
    with patch("app.agents.prompts.os.listdir", return_value=["readme.txt", "notes"]):
        result = get_available_prompts()
        assert result == []

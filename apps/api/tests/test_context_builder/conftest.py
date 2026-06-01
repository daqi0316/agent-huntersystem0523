"""conftest — mock tiktoken so tests run without the extra package."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Mock tiktoken before context_builder imports it
_CHAR_TOKENS = 4  # ~4 chars ≈ 1 token for typical English text
_mock_encoding = MagicMock()
_mock_encoding.encode = lambda text, **_: [1] * max(1, len(text) // _CHAR_TOKENS)
sys.modules["tiktoken"] = MagicMock(
    encoding_for_model=lambda _model: _mock_encoding,
    get_encoding=lambda _name: _mock_encoding,
)

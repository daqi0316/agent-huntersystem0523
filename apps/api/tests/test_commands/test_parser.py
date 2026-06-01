"""Tests for CommandParser — 解析器覆盖 8 个别名、4 种 flag 形态、管道、转义."""

from __future__ import annotations

import pytest

from app.commands.parser import CommandParser
from app.commands.types import ParsedCommand


@pytest.fixture
def parser() -> CommandParser:
    return CommandParser()


# ── 非命令输入（None passthrough）─────────────────────


@pytest.mark.parametrize("inp", ["", "   ", "//hello world", "//  ", "hello world"])
def test_non_command_returns_none(parser: CommandParser, inp: str) -> None:
    assert parser.parse(inp) is None


@pytest.mark.parametrize("inp", ["/", "/   "])
def test_slash_alone_returns_none(parser: CommandParser, inp: str) -> None:
    assert parser.parse(inp) is None


def test_non_string_raises(parser: CommandParser) -> None:
    with pytest.raises(ValueError, match="input must be a string"):
        parser.parse(None)  # type: ignore[arg-type]


# ── 基础命令名解析 ────────────────────────────────────


def test_simple_command(parser: CommandParser) -> None:
    r = parser.parse("/help")
    assert r is not None
    assert r.name == "help"
    assert r.raw_name == "help"
    assert r.args == []
    assert r.flags == {}


def test_simple_command_no_alias(parser: CommandParser) -> None:
    r = parser.parse("/restart")
    assert r is not None
    assert r.name == "restart"
    assert r.raw_name == "restart"


def test_command_with_positional_args(parser: CommandParser) -> None:
    r = parser.parse("/read candidate cand_001")
    assert r is not None
    assert r.name == "read"
    assert r.args == ["candidate", "cand_001"]


def test_command_case_insensitive(parser: CommandParser) -> None:
    r = parser.parse("/HELP")
    assert r is not None
    assert r.name == "help"


def test_command_with_surrounding_whitespace(parser: CommandParser) -> None:
    r = parser.parse("   /help me   ")
    assert r is not None
    assert r.name == "help"
    assert r.args == ["me"]


# ── flag 解析 ─────────────────────────────────────────


def test_flag_with_equals(parser: CommandParser) -> None:
    r = parser.parse("/list candidates --status=active")
    assert r is not None
    assert r.name == "list"
    assert r.args == ["candidates"]
    assert r.flags == {"status": "active"}


def test_flag_bare_boolean(parser: CommandParser) -> None:
    r = parser.parse("/list candidates --no-color")
    assert r is not None
    assert r.flags == {"no-color": True}


def test_flag_space_separated_value(parser: CommandParser) -> None:
    r = parser.parse("/list candidates --limit 10 --offset 20")
    assert r is not None
    assert r.args == ["candidates"]
    assert r.flags == {"limit": "10", "offset": "20"}


def test_flag_mixed_forms(parser: CommandParser) -> None:
    r = parser.parse("/search Java --type=candidate --limit 5 --semantic")
    assert r is not None
    assert r.args == ["Java"]
    assert r.flags == {"type": "candidate", "limit": "5", "semantic": True}


# ── 引号包裹 ──────────────────────────────────────────


def test_quoted_arg_with_spaces(parser: CommandParser) -> None:
    r = parser.parse('/read candidate "zhang san"')
    assert r is not None
    assert r.args == ["candidate", "zhang san"]


def test_escaped_quote_in_arg(parser: CommandParser) -> None:
    r = parser.parse(r'/read candidate "zhang \"san\""')
    assert r is not None
    assert r.args == ["candidate", 'zhang "san"']


def test_unclosed_quote_raises(parser: CommandParser) -> None:
    with pytest.raises(ValueError, match="未闭合"):
        parser.parse('/read candidate "zhang san')


# ── 8 个别名展开 ─────────────────────────────────────


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("/r", "restart"),
        ("/p", "pause"),
        ("/s", "status"),
        ("/h", "help"),
        ("/n", "new"),
        ("/l", "list"),
        ("/d", "debug"),
    ],
)
def test_all_aliases_resolve(parser: CommandParser, alias: str, expected: str) -> None:
    r = parser.parse(alias)
    assert r is not None
    assert r.name == expected


def test_raw_name_preserved(parser: CommandParser) -> None:
    """raw_name 保留用户输入的形态，name 是展开后的规范名."""
    r = parser.parse("/r --force")
    assert r is not None
    assert r.name == "restart"
    assert r.raw_name == "r"


# ── 管道解析（v1 仅解析不执行）─────────────────────


def test_pipe_parsed(parser: CommandParser) -> None:
    r = parser.parse("/list candidates | /filter score>80")
    assert r is not None
    assert r.name == "list"
    assert r.args == ["candidates"]
    assert r.pipe_target == "/filter score>80"
    assert r.has_pipe


def test_pipe_left_required(parser: CommandParser) -> None:
    with pytest.raises(ValueError, match="管道左侧"):
        parser.parse("| /filter score>80")


# ── 非法命令名 ───────────────────────────────────────


def test_invalid_name_with_special_chars_raises(parser: CommandParser) -> None:
    with pytest.raises(ValueError, match="非法命令名"):
        parser.parse("/bad@cmd")


def test_name_starting_with_digit_raises(parser: CommandParser) -> None:
    with pytest.raises(ValueError, match="非法命令名"):
        parser.parse("/123abc")


# ── is_command 快速判断 ──────────────────────────────


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("/help", True),
        ("//help", False),
        ("help", False),
        ("/   ", False),
        ("/", False),
        ("", False),
        ("   ", False),
        (None, False),  # type: ignore[list-item]
    ],
)
def test_is_command(parser: CommandParser, inp: str, expected: bool) -> None:
    assert parser.is_command(inp) is expected


# ── raw 字段保留原输入 ───────────────────────────────


def test_raw_preserved(parser: CommandParser) -> None:
    raw = "   /help me please   "
    r = parser.parse(raw)
    assert r is not None
    assert r.raw == raw

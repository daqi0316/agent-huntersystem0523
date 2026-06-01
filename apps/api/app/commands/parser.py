"""CommandParser — 解析用户输入的命令字符串."""

from __future__ import annotations

import re
from typing import Any

from app.commands.types import ParsedCommand


_ALIASES: dict[str, str] = {
    "r": "restart",
    "p": "pause",
    "s": "status",
    "h": "help",
    "n": "new",
    "l": "list",
    "d": "debug",
}
_ALIASES_REVERSE: dict[str, str] = {v: k for k, v in _ALIASES.items()}

_CANONICAL_PREFERRED_SHORT: dict[str, str] = {}

_PIPE_TOKEN = "|"
_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
_FLAG_EQ_RE = re.compile(r"^--([a-zA-Z][a-zA-Z0-9_-]*)=(.*)$")
_FLAG_BARE_RE = re.compile(r"^--([a-zA-Z][a-zA-Z0-9_-]*)$")


class CommandParser:
    __slots__ = ()

    def parse(self, input_str: str) -> ParsedCommand | None:
        if not isinstance(input_str, str):
            raise ValueError("input must be a string")
        stripped = input_str.strip()
        if not stripped or stripped.startswith("//"):
            return None
        if stripped.startswith("|"):
            raise ValueError("管道左侧必须包含命令")
        if not stripped.startswith("/"):
            return None
        body = stripped[1:].strip()
        if not body:
            return None
        pipe_target: str | None = None
        if _PIPE_TOKEN in body:
            body, pipe_target_raw = body.split(_PIPE_TOKEN, 1)
            pipe_target = pipe_target_raw.strip()
            body = body.strip()
            if not body:
                raise ValueError("管道左侧必须包含命令")
        tokens = self._tokenize(body)
        if not tokens:
            raise ValueError("命令体为空")
        raw_name = tokens[0].lower()
        rest = tokens[1:]
        if not _NAME_RE.match(raw_name):
            raise ValueError(f"非法命令名: {raw_name!r}")
        canonical_name = _ALIASES.get(raw_name, raw_name)
        if not _NAME_RE.match(canonical_name):
            raise ValueError(f"别名映射后命令名非法: {canonical_name!r}")
        args: list[str] = []
        flags: dict[str, str | bool] = {}
        i = 0
        while i < len(rest):
            token = rest[i]
            m_eq = _FLAG_EQ_RE.match(token)
            if m_eq:
                flags[m_eq.group(1)] = m_eq.group(2)
                i += 1
                continue
            m_bare = _FLAG_BARE_RE.match(token)
            if m_bare:
                flag_name = m_bare.group(1)
                if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                    flags[flag_name] = rest[i + 1]
                    i += 2
                else:
                    flags[flag_name] = True
                    i += 1
                continue
            args.append(token)
            i += 1
        return ParsedCommand(
            name=canonical_name,
            raw_name=raw_name,
            args=args,
            flags=flags,
            pipe_target=pipe_target,
            raw=input_str,
        )

    @staticmethod
    def _tokenize(body: str) -> list[str]:
        tokens: list[str] = []
        current: list[str] = []
        in_quote = False
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == '"':
                in_quote = not in_quote
                current.append('"')
                i += 1
                continue
            if ch == "\\" and i + 1 < len(body):
                current.append(body[i + 1])
                i += 2
                continue
            if ch.isspace() and not in_quote:
                if current:
                    tokens.append("".join(current))
                    current = []
                i += 1
                continue
            current.append(ch)
            i += 1
        if current:
            tokens.append("".join(current))
        if in_quote:
            raise ValueError("未闭合的双引号")
        return CommandParser._strip_delimiter_quotes(tokens)

    @staticmethod
    def _strip_delimiter_quotes(tokens: list[str]) -> list[str]:
        result: list[str] = []
        for tok in tokens:
            if (
                len(tok) >= 2
                and tok[0] == '"'
                and tok[-1] == '"'
                and any(ch.isspace() for ch in tok[1:-1])
            ):
                result.append(tok[1:-1])
            else:
                result.append(tok)
        return result

    def is_command(self, input_str: str) -> bool:
        if not isinstance(input_str, str):
            return False
        stripped = input_str.strip()
        if not stripped or stripped.startswith("//"):
            return False
        return stripped.startswith("/") and len(stripped) > 1


parser = CommandParser()

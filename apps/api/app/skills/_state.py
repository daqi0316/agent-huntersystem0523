"""v0.7: Skill enable/disable 状态持久化。

状态文件 .omo/skill_state.json:
  {
    "weather": {"enabled": true},
    "web_search": {"enabled": false},
    ...
  }

未列出的 skill 默认 enabled (新装 skill 自动可用)。
state 是 per-host 状态 (gitignore), 不同机器独立。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path(__file__).resolve().parents[3] / ".omo" / "skill_state.json"


def _ensure_parent() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, dict]:
    """Load enable/disable state. 缺文件返空 dict."""
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load skill_state.json: %s", e)
        return {}


def save_state(state: dict[str, dict]) -> None:
    """Persist state to .omo/skill_state.json (gitignored)."""
    _ensure_parent()
    _STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_enabled(skill_name: str, state: dict[str, dict] | None = None) -> bool:
    """Check if skill is enabled. 默认 enabled (新装 skill 自动可用)."""
    if state is None:
        state = load_state()
    entry = state.get(skill_name)
    if entry is None:
        return True
    return bool(entry.get("enabled", True))


def set_enabled(skill_name: str, enabled: bool) -> None:
    """Set enable/disable for a skill, persist immediately."""
    state = load_state()
    state[skill_name] = {"enabled": enabled}
    save_state(state)

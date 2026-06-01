"""Tests for interview built-in tools — schedule_interview, record_feedback.

Note: schedule_interview and record_feedback require real DB sessions.
These tests verify the tool schema definitions are valid.
"""

from app.tools.interview import tools, handlers


def test_interview_tools_defined():
    assert len(tools) == 3
    names = [t["function"]["name"] for t in tools]
    assert "schedule_interview" in names
    assert "record_feedback" in names
    assert "cancel_interview" in names


def test_interview_handlers_registered():
    assert "schedule_interview" in handlers
    assert "record_feedback" in handlers
    assert "cancel_interview" in handlers

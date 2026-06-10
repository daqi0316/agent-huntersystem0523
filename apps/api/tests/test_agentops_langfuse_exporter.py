from typing import override

import pytest

from app.agentops.core.schemas import ScoreEvent, TraceEvent
from app.agentops.exporters.langfuse_exporter import LangfuseExporter

pytestmark = pytest.mark.asyncio


class FakeLangfuseClient:
    def __init__(self):
        self.scores: list[dict[str, object]] = []
        self.flushed: bool = False
        self.shutdown_called: bool = False

    def score(self, **kwargs: object) -> object:
        self.scores.append(kwargs)
        return None

    def flush(self) -> object:
        self.flushed = True
        return None

    def shutdown(self) -> object:
        self.shutdown_called = True
        return None


class FailingLangfuseClient(FakeLangfuseClient):
    @override
    def score(self, **kwargs: object) -> object:
        _ = kwargs
        raise RuntimeError("score down")

    @override
    def flush(self) -> object:
        raise RuntimeError("flush down")

    @override
    def shutdown(self) -> object:
        raise RuntimeError("shutdown down")


async def test_langfuse_exporter_disabled_is_noop():
    client = FakeLangfuseClient()
    exporter = LangfuseExporter(enabled=False, client=client)

    await exporter.export(ScoreEvent(name="score", score_name="quality", value=1, trace_id="trace-1"))
    await exporter.flush()
    await exporter.shutdown()

    assert client.scores == []
    assert client.flushed is False
    assert client.shutdown_called is False


async def test_langfuse_exporter_writes_score_with_fake_client():
    client = FakeLangfuseClient()
    exporter = LangfuseExporter(enabled=True, client=client)

    await exporter.export(
        ScoreEvent(
            name="score.screening",
            score_name="screening_reasonability",
            value=4,
            comment="ok",
            trace_id="trace-1",
            metadata={"rubric": "v1"},
        )
    )

    assert client.scores == [
        {
            "trace_id": "trace-1",
            "name": "screening_reasonability",
            "value": 4,
            "comment": "ok",
            "metadata": {"rubric": "v1"},
        }
    ]


async def test_langfuse_exporter_ignores_non_score_events_for_now():
    client = FakeLangfuseClient()
    exporter = LangfuseExporter(enabled=True, client=client)

    await exporter.export(TraceEvent(name="trace"))

    assert client.scores == []


async def test_langfuse_exporter_isolates_client_failures():
    exporter = LangfuseExporter(enabled=True, client=FailingLangfuseClient())

    await exporter.export(ScoreEvent(name="score", score_name="quality", value=1, trace_id="trace-1"))
    await exporter.flush()
    await exporter.shutdown()


async def test_langfuse_exporter_without_keys_does_not_import_sdk():
    exporter = LangfuseExporter(enabled=True, client=None, public_key="", secret_key="")

    await exporter.export(ScoreEvent(name="score", score_name="quality", value=1, trace_id="trace-1"))

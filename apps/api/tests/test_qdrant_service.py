"""Unit tests for app/services/qdrant_service.py — Qdrant vector storage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.qdrant_service import QdrantService


@pytest.fixture
def qdrant_client():
    return AsyncMock()


@pytest.fixture
def service(qdrant_client):
    return QdrantService(client=qdrant_client, collection="test_collection")


class TestInit:
    def test_stores_client_and_collection(self, qdrant_client):
        svc = QdrantService(client=qdrant_client, collection="my_coll")
        assert svc.client is qdrant_client
        assert svc.collection == "my_coll"

    def test_vector_size_none_by_default(self, qdrant_client):
        svc = QdrantService(client=qdrant_client, collection="c")
        assert svc._vector_size is None


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_collection_exists_skips_creation(self, service, qdrant_client):
        mock_collection = MagicMock()
        mock_collection.name = "test_collection"
        qdrant_client.get_collections.return_value = MagicMock(
            collections=[mock_collection]
        )

        await service.ensure_collection(vector_size=128)

        qdrant_client.get_collections.assert_awaited_once()
        qdrant_client.create_collection.assert_not_called()
        assert service._vector_size == 128

    @pytest.mark.asyncio
    async def test_collection_not_exists_creates(self, service, qdrant_client):
        qdrant_client.get_collections.return_value = MagicMock(collections=[])

        await service.ensure_collection(vector_size=256)

        qdrant_client.create_collection.assert_awaited_once()
        call_kwargs = qdrant_client.create_collection.await_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["vectors_config"].size == 256

    @pytest.mark.asyncio
    async def test_get_collections_fails_still_creates(self, service, qdrant_client):
        qdrant_client.get_collections.side_effect = Exception("Qdrant down")

        await service.ensure_collection(vector_size=64)

        qdrant_client.create_collection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_collection_failure_raises(self, service, qdrant_client):
        qdrant_client.get_collections.return_value = MagicMock(collections=[])
        qdrant_client.create_collection.side_effect = Exception("Create failed")

        with pytest.raises(Exception, match="Create failed"):
            await service.ensure_collection(vector_size=128)


class TestUpsert:
    @pytest.mark.asyncio
    async def test_successful_upsert(self, service, qdrant_client):
        await service.upsert(
            point_id="p1",
            vector=[0.1, 0.2, 0.3],
            payload={"key": "value"},
        )
        qdrant_client.upsert.assert_awaited_once()
        args = qdrant_client.upsert.await_args
        assert args.kwargs["collection_name"] == "test_collection"
        points = args.kwargs["points"]
        assert len(points) == 1
        assert points[0].id == "p1"
        assert points[0].vector == [0.1, 0.2, 0.3]
        assert points[0].payload == {"key": "value"}

    @pytest.mark.asyncio
    async def test_upsert_without_payload(self, service, qdrant_client):
        await service.upsert(point_id="p2", vector=[0.5, 0.6])
        args = qdrant_client.upsert.await_args
        points = args.kwargs["points"]
        assert points[0].payload == {}

    @pytest.mark.asyncio
    async def test_upsert_failure_raises(self, service, qdrant_client):
        qdrant_client.upsert.side_effect = Exception("Upsert failed")
        with pytest.raises(Exception, match="Upsert failed"):
            await service.upsert(point_id="p1", vector=[0.1])


class TestDelete:
    @pytest.mark.asyncio
    async def test_successful_delete(self, service, qdrant_client):
        await service.delete(point_id="point-1")
        qdrant_client.delete.assert_awaited_once()
        args = qdrant_client.delete.await_args
        assert args.kwargs["collection_name"] == "test_collection"

    @pytest.mark.asyncio
    async def test_delete_failure_raises(self, service, qdrant_client):
        qdrant_client.delete.side_effect = Exception("Delete failed")
        with pytest.raises(Exception, match="Delete failed"):
            await service.delete(point_id="p1")


class TestSearch:
    @pytest.mark.asyncio
    async def test_successful_search(self, service, qdrant_client):
        from qdrant_client.models import ScoredPoint

        mock_point = MagicMock(spec=ScoredPoint)
        mock_point.id = "p1"
        mock_point.score = 0.95
        mock_point.payload = {"text": "hello"}
        qdrant_client.search.return_value = [mock_point]

        results = await service.search(vector=[0.1, 0.2], top_k=5)

        assert len(results) == 1
        assert results[0]["id"] == "p1"
        assert results[0]["score"] == 0.95
        assert results[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_search_with_score_threshold(self, service, qdrant_client):
        qdrant_client.search.return_value = []
        await service.search(vector=[0.1], top_k=3, score_threshold=0.7)
        qdrant_client.search.assert_awaited_once()
        assert qdrant_client.search.await_args.kwargs["score_threshold"] == 0.7

    @pytest.mark.asyncio
    async def test_search_empty_results(self, service, qdrant_client):
        qdrant_client.search.return_value = []
        results = await service.search(vector=[0.1])
        assert results == []

    @pytest.mark.asyncio
    async def test_search_failure_returns_empty(self, service, qdrant_client):
        qdrant_client.search.side_effect = Exception("Search failed")
        results = await service.search(vector=[0.1])
        assert results == []


class TestScrollByFilter:
    @pytest.mark.asyncio
    async def test_successful_scroll(self, service, qdrant_client):
        mock_point = MagicMock()
        mock_point.id = "p1"
        mock_point.payload = {"text": "data"}
        qdrant_client.scroll.return_value = ([mock_point], None)

        results = await service.scroll_by_filter(limit=50)

        assert len(results) == 1
        assert results[0]["id"] == "p1"
        assert results[0]["text"] == "data"

    @pytest.mark.asyncio
    async def test_scroll_failure_returns_empty(self, service, qdrant_client):
        qdrant_client.scroll.side_effect = Exception("Scroll failed")
        results = await service.scroll_by_filter()
        assert results == []


class TestCount:
    @pytest.mark.asyncio
    async def test_successful_count(self, service, qdrant_client):
        from qdrant_client.models import ScoredPoint

        mock_count_result = MagicMock()
        mock_count_result.count = 42
        qdrant_client.count.return_value = mock_count_result

        result = await service.count()
        assert result == 42

    @pytest.mark.asyncio
    async def test_count_failure_returns_zero(self, service, qdrant_client):
        qdrant_client.count.side_effect = Exception("Count failed")
        result = await service.count()
        assert result == 0

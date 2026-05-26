from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.response import error, ok_list, ok_or_404, success


class TestSuccess:
    def test_returns_data(self):
        assert success("hello") == {"success": True, "data": "hello"}

    def test_returns_none(self):
        assert success() == {"success": True, "data": None}


class TestOkList:
    def test_basic(self):
        result = ok_list([1, 2], total=2)
        assert result["success"] is True
        assert result["data"] == [1, 2]
        assert result["total"] == 2
        assert result["skip"] == 0
        assert result["limit"] == 20

    def test_with_pagination(self):
        result = ok_list([], total=0, skip=10, limit=10)
        assert result["skip"] == 10
        assert result["limit"] == 10


class TestError:
    def test_message_only(self):
        resp = error("something went wrong")
        assert resp.status_code == 400
        assert resp.body is not None

    def test_custom_status(self):
        resp = error("not found", status_code=404)
        assert resp.status_code == 404

    def test_with_details(self):
        resp = error("validation error", details=["field x required", "field y too long"])
        assert resp.status_code == 400


class TestOkOr404:
    def test_returns_value(self):
        assert ok_or_404("hello") == "hello"

    def test_raises_404(self):
        with pytest.raises(HTTPException) as exc:
            ok_or_404(None)
        assert exc.value.status_code == 404

    def test_custom_detail(self):
        with pytest.raises(HTTPException) as exc:
            ok_or_404(None, detail="custom msg")
        assert exc.value.detail == "custom msg"

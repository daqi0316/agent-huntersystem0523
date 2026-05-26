"""Unit tests for app/core/response.py — unified response helpers."""

import json

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.response import error, ok_list, ok_or_404, success


class TestSuccess:
    def test_with_data(self):
        result = success({"id": "abc"})
        assert result == {"success": True, "data": {"id": "abc"}}

    def test_with_none(self):
        result = success()
        assert result == {"success": True, "data": None}

    def test_with_list(self):
        result = success([1, 2, 3])
        assert result == {"success": True, "data": [1, 2, 3]}

    def test_with_string(self):
        result = success("ok")
        assert result == {"success": True, "data": "ok"}

    def test_with_int(self):
        result = success(42)
        assert result == {"success": True, "data": 42}


class TestOkList:
    def test_basic(self):
        result = ok_list(["a", "b"], total=10)
        assert result["success"] is True
        assert result["data"] == ["a", "b"]
        assert result["total"] == 10
        assert result["skip"] == 0
        assert result["limit"] == 20

    def test_custom_pagination(self):
        result = ok_list([], total=0, skip=10, limit=5)
        assert result["skip"] == 10
        assert result["limit"] == 5

    def test_empty_list(self):
        result = ok_list([], total=0)
        assert result["data"] == []
        assert result["total"] == 0


class TestError:
    def test_basic(self):
        resp = error("出错了")
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert body == {"success": False, "error": "出错了"}

    def test_custom_status(self):
        resp = error("未找到", status_code=404)
        assert resp.status_code == 404
        assert json.loads(resp.body)["error"] == "未找到"

    def test_with_details(self):
        resp = error("校验失败", details=[{"field": "name", "msg": "required"}])
        body = json.loads(resp.body)
        assert body["details"] == [{"field": "name", "msg": "required"}]

    def test_default_status_code(self):
        resp = error("错误")
        assert resp.status_code == 400


class TestOkOr404:
    def test_found_returns_value(self):
        result = ok_or_404({"id": 1})
        assert result == {"id": 1}

    def test_found_none_falsy(self):
        """ok_or_404 should also return 0 / empty string as valid results."""
        result = ok_or_404(0)
        assert result == 0

    def test_not_found_raises(self):
        with pytest.raises(HTTPException) as exc:
            ok_or_404(None)
        assert exc.value.status_code == 404
        assert exc.value.detail == "资源不存在"

    def test_not_found_custom_message(self):
        with pytest.raises(HTTPException) as exc:
            ok_or_404(None, detail="自定义未找到")
        assert exc.value.detail == "自定义未找到"

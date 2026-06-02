"""test_user_memory.py — Phase 3 USER 持久化集成测试。"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_user_id, get_current_user
from app.agents.prompts import load_user_memory


@pytest.fixture
def temp_settings_dir(tmp_path):
    settings = tmp_path / "users"
    yield settings
    import shutil
    shutil.rmtree(settings, ignore_errors=True)


@pytest.fixture
def mock_user():
    return {"user_id": "test-user-001", "role": "user", "name": "Test User"}


@pytest.fixture
def mock_admin():
    return {"user_id": "admin-001", "role": "admin", "name": "Admin User"}


@pytest.fixture
def client():
    return TestClient(app)


class TestLoadUserMemory:
    """load_user_memory 核心逻辑测试（绕过 env SETTINGS_DIR，直接测文件逻辑）。"""

    def test_first_read_copies_from_template(self, temp_settings_dir):
        user_id = "user-001"
        settings_dir = str(temp_settings_dir)

        with patch.dict(os.environ, {"SETTINGS_DIR": settings_dir}):
            content = load_user_memory(user_id)

        assert content, "Template should exist and be non-empty"

        user_file = temp_settings_dir / user_id / "memory.md"
        assert user_file.exists(), f"User file should be created at {user_file}"

    def test_second_read_returns_same_content(self, temp_settings_dir):
        user_id = "user-002"
        settings_dir = str(temp_settings_dir)

        with patch.dict(os.environ, {"SETTINGS_DIR": settings_dir}):
            content1 = load_user_memory(user_id)
            content2 = load_user_memory(user_id)
        assert content1 == content2, "Subsequent reads should return same content"

    def test_different_users_get_independent_files(self, temp_settings_dir):
        user1 = "user-010"
        user2 = "user-011"
        settings_dir = str(temp_settings_dir)

        with patch.dict(os.environ, {"SETTINGS_DIR": settings_dir}):
            load_user_memory(user1)
            load_user_memory(user2)

        file1 = temp_settings_dir / user1 / "memory.md"
        file2 = temp_settings_dir / user2 / "memory.md"
        assert file1.exists() and file2.exists()
        assert file1.resolve() != file2.resolve(), "Each user gets own file"

    def test_user_file_written_in_utf8(self, temp_settings_dir):
        user_id = "user-003"
        settings_dir = str(temp_settings_dir)

        with patch.dict(os.environ, {"SETTINGS_DIR": settings_dir}):
            load_user_memory(user_id)

        user_file = temp_settings_dir / user_id / "memory.md"
        assert user_file.exists()
        content = user_file.read_text(encoding="utf-8")
        assert content

    def test_write_then_read_returns_updated_content(self, temp_settings_dir):
        user_id = "user-004"
        settings_dir = str(temp_settings_dir)
        user_file = temp_settings_dir / user_id / "memory.md"

        # Initial read (creates from template)
        with patch.dict(os.environ, {"SETTINGS_DIR": settings_dir}):
            initial = load_user_memory(user_id)

        # Write new content directly
        new_content = "# 我的自定义记忆\n\n新内容"
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text(new_content, encoding="utf-8")

        # Invalidate cache so next read goes to disk
        from app.agents.prompts.cache_manager import invalidate_cache
        invalidate_cache(f"user:{user_id}")

        # Read again
        with patch.dict(os.environ, {"SETTINGS_DIR": settings_dir}):
            updated = load_user_memory(user_id)

        assert updated == new_content, "After invalidation, should read updated file"


class TestUserMemoryAPI:
    """API 端点测试。"""

    def test_get_my_memory_requires_auth(self, client):
        response = client.get("/api/v1/users/me/memory")
        assert response.status_code == 401

    def test_get_my_memory_returns_content(self, client, mock_user, temp_settings_dir):
        app.dependency_overrides[get_current_user_id] = lambda: mock_user["user_id"]
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch.dict(os.environ, {"SETTINGS_DIR": str(temp_settings_dir)}):
            response = client.get("/api/v1/users/me/memory", headers={"Authorization": "Bearer test"})

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["user_id"] == mock_user["user_id"]

        app.dependency_overrides.clear()

    def test_put_my_memory_updates_file(self, client, mock_user, temp_settings_dir):
        app.dependency_overrides[get_current_user_id] = lambda: mock_user["user_id"]
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch.dict(os.environ, {"SETTINGS_DIR": str(temp_settings_dir)}):
            new_content = "# 我的记忆\n\n测试内容"
            response = client.put(
                "/api/v1/users/me/memory",
                json={"content": new_content},
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == new_content

        user_file = temp_settings_dir / mock_user["user_id"] / "memory.md"
        assert user_file.read_text(encoding="utf-8") == new_content

        app.dependency_overrides.clear()

    def test_admin_can_read_other_user_memory(self, client, mock_admin, temp_settings_dir):
        target_user = "target-user-001"
        app.dependency_overrides[get_current_user] = lambda: mock_admin

        with patch.dict(os.environ, {"SETTINGS_DIR": str(temp_settings_dir)}):
            load_user_memory(target_user)  # create file first

            response = client.get(
                f"/api/v1/users/{target_user}/memory",
                headers={"Authorization": "Bearer admin-test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == target_user

        app.dependency_overrides.clear()

    def test_non_admin_cannot_read_other_user_memory(self, client, mock_user, temp_settings_dir):
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch.dict(os.environ, {"SETTINGS_DIR": str(temp_settings_dir)}):
            response = client.get(
                "/api/v1/users/other-user/memory",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 403

        app.dependency_overrides.clear()


class TestUserMemoryEnabledFlag:
    """USER_MEMORY_ENABLED=false 时 API 返回 404。"""

    def test_get_memory_404_when_disabled(self, client, mock_user, temp_settings_dir):
        app.dependency_overrides[get_current_user_id] = lambda: mock_user["user_id"]
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch.dict(os.environ, {"USER_MEMORY_ENABLED": "false", "SETTINGS_DIR": str(temp_settings_dir)}):
            response = client.get(
                "/api/v1/users/me/memory",
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 404

        app.dependency_overrides.clear()

    def test_put_memory_404_when_disabled(self, client, mock_user, temp_settings_dir):
        app.dependency_overrides[get_current_user_id] = lambda: mock_user["user_id"]
        app.dependency_overrides[get_current_user] = lambda: mock_user

        with patch.dict(os.environ, {"USER_MEMORY_ENABLED": "false", "SETTINGS_DIR": str(temp_settings_dir)}):
            response = client.put(
                "/api/v1/users/me/memory",
                json={"content": "test"},
                headers={"Authorization": "Bearer test"},
            )

        assert response.status_code == 404

        app.dependency_overrides.clear()

"""Snapshot Manager — 状态快照持久化。

基于 SqliteSaver + 自定义快照元数据表。
每步 checkpoint 自动创建快照，支持按 task_id 恢复和时间线查询。
"""

from __future__ import annotations

import json
import hashlib
import logging
import sqlite3
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SNAPSHOT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "snapshots.db",
)


class SnapshotManager:
    def __init__(self, db_path: str = SNAPSHOT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                parent_snapshot_id TEXT,
                state_json TEXT NOT NULL,
                state_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                agent_type TEXT,
                step_name TEXT,
                description TEXT,
                is_auto INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snap_task ON snapshots(task_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snap_task_agent ON snapshots(task_id, agent_type)
        """)
        conn.commit()
        conn.close()

    def create(
        self,
        state: dict,
        task_id: str,
        agent_type: str | None = None,
        step_name: str | None = None,
        description: str = "",
        is_auto: bool = True,
        parent_snapshot_id: str | None = None,
    ) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        state_json = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()[:16]
        snapshot_id = f"snap_{task_id[:8]}_{agent_type or 'global'}_{state_hash}"

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO snapshots
                   (snapshot_id, task_id, parent_snapshot_id, state_json, state_hash,
                    created_at, agent_type, step_name, description, is_auto)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_id, task_id, parent_snapshot_id, state_json, state_hash,
                 timestamp, agent_type, step_name, description, 1 if is_auto else 0),
            )
            conn.commit()
        finally:
            conn.close()

        return snapshot_id

    def restore(self, snapshot_id: str) -> dict | None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT state_json FROM snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()

    def get_latest(self, task_id: str) -> dict | None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT state_json, snapshot_id FROM snapshots WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return {"state": json.loads(row[0]), "snapshot_id": row[1]}
            return None
        finally:
            conn.close()

    def list_by_task(self, task_id: str, agent_type: str | None = None) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            if agent_type:
                cursor = conn.execute(
                    """SELECT snapshot_id, created_at, agent_type, step_name, description, is_auto
                       FROM snapshots WHERE task_id = ? AND agent_type = ? ORDER BY created_at DESC""",
                    (task_id, agent_type),
                )
            else:
                cursor = conn.execute(
                    """SELECT snapshot_id, created_at, agent_type, step_name, description, is_auto
                       FROM snapshots WHERE task_id = ? ORDER BY created_at DESC""",
                    (task_id,),
                )
            return [
                {
                    "snapshot_id": r[0],
                    "created_at": r[1],
                    "agent_type": r[2],
                    "step_name": r[3],
                    "description": r[4],
                    "is_auto": bool(r[5]),
                }
                for r in cursor.fetchall()
            ]
        finally:
            conn.close()

    def clear_task(self, task_id: str):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM snapshots WHERE task_id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()

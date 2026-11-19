import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.paths import DB_PATH, ensure_directories


class ActiveTaskExistsError(Exception):
    """Raised when the same profile already has a queued or running task."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    ensure_directories()
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def initialize() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                profile_url TEXT NOT NULL,
                interval TEXT NOT NULL,
                max_counts INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        progress_columns = {
            "mode": "TEXT NOT NULL DEFAULT 'post'",
            "stage": "TEXT NOT NULL DEFAULT 'queued'",
            "total_items": "INTEGER NOT NULL DEFAULT 0",
            "processed_items": "INTEGER NOT NULL DEFAULT 0",
            "downloaded_items": "INTEGER NOT NULL DEFAULT 0",
            "failed_items": "INTEGER NOT NULL DEFAULT 0",
            "current_item": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in progress_columns.items():
            if name not in existing_columns:
                connection.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_task_per_profile
            ON tasks(profile_url)
            WHERE status IN ('queued', 'running')
            """
        )


def create_task(
    profile_url: str, interval: str, max_counts: int, mode: str = "post"
) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    timestamp = _now()
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks
                    (id, profile_url, interval, max_counts, mode, status, message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', '等待开始', ?, ?)
                """,
                (task_id, profile_url, interval, max_counts, mode, timestamp, timestamp),
            )
    except sqlite3.IntegrityError as exc:
        raise ActiveTaskExistsError(profile_url) from exc
    return get_task(task_id)


def update_task(task_id: str, status: str, message: str) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE tasks SET status = ?, message = ?, updated_at = ? WHERE id = ?",
            (status, message, _now(), task_id),
        )


def update_progress(task_id: str, **values: Any) -> None:
    allowed = {
        "stage",
        "total_items",
        "processed_items",
        "downloaded_items",
        "failed_items",
        "current_item",
        "message",
    }
    updates = {key: value for key, value in values.items() if key in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with _connect() as connection:
        connection.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?",
            (*updates.values(), task_id),
        )


def get_task(task_id: str) -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(task_id)
    return dict(row)


def list_tasks(limit: int = 30) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


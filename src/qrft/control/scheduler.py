"""SQLite 原子时间片租约调度：超时回收、重复领取保护、完成幂等。"""

from __future__ import annotations

import sqlite3
import time
import uuid


def init_schema(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS task_controls(task_id INTEGER PRIMARY KEY, cancelled INTEGER NOT NULL DEFAULT 0, paused INTEGER NOT NULL DEFAULT 0)"
    )
    controls = {row[1] for row in db.execute("PRAGMA table_info(task_controls)")}
    if "paused" not in controls:
        db.execute("ALTER TABLE task_controls ADD COLUMN paused INTEGER NOT NULL DEFAULT 0")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS slices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            owner TEXT,
            lease_until REAL,
            attempts INTEGER NOT NULL DEFAULT 0,
            UNIQUE(video_id, start_ms, end_ms)
        )
        """
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(slices)")}
    for column, kind in (("checkpoint_ms", "INTEGER NOT NULL DEFAULT 0"), ("lease_token", "TEXT")):
        if column not in columns:
            db.execute(f"ALTER TABLE slices ADD COLUMN {column} {kind}")
    db.execute("CREATE INDEX IF NOT EXISTS slices_state_lease ON slices(state, lease_until)")


def add_slices(
    db: sqlite3.Connection,
    video_id: int,
    duration_seconds: float,
    slice_ms: int = 30000,
    overlap_ms: int = 1000,
) -> int:
    if slice_ms <= 0 or overlap_ms < 0 or overlap_ms >= slice_ms:
        raise ValueError("invalid slice/overlap settings")
    duration_ms = max(1, int(duration_seconds * 1000))
    step = slice_ms - overlap_ms
    count = 0
    for start in range(0, duration_ms, step):
        end = min(start + slice_ms, duration_ms)
        db.execute(
            "INSERT OR IGNORE INTO slices(video_id,start_ms,end_ms) VALUES (?,?,?)",
            (video_id, start, end),
        )
        count += 1
        if end == duration_ms:
            break
    return count


def claim(
    db: sqlite3.Connection, node_id: str, lease_seconds: int = 120, task_id: int | None = None
) -> dict | None:
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    if (
        db.execute(
            "SELECT 1 FROM slices WHERE state='leased' AND owner=? AND lease_until>? LIMIT 1",
            (node_id, now),
        ).fetchone()
        is not None
    ):
        db.commit()
        return None
    row = db.execute(
        """
        SELECT s.id, s.video_id, s.start_ms, s.end_ms, v.path, v.task_id, s.attempts, s.checkpoint_ms
        FROM slices s JOIN videos v ON v.id=s.video_id
        WHERE (s.state='pending' OR (s.state='leased' AND s.lease_until <= ?))
        AND NOT EXISTS (SELECT 1 FROM task_controls c WHERE c.task_id=v.task_id AND (c.cancelled=1 OR c.paused=1))
        AND (? IS NULL OR v.task_id=?)
        ORDER BY s.id LIMIT 1
        """,
        (now, task_id, task_id),
    ).fetchone()
    if row is None:
        db.commit()
        return None
    lease_token = uuid.uuid4().hex
    db.execute(
        "UPDATE slices SET state='leased', owner=?, lease_until=?, attempts=attempts+1, lease_token=? WHERE id=?",
        (node_id, now + lease_seconds, lease_token, row["id"]),
    )
    db.commit()
    return {
        **dict(row),
        "owner": node_id,
        "lease_until": now + lease_seconds,
        "lease_token": lease_token,
    }


def complete(
    db: sqlite3.Connection, slice_id: int, node_id: str, lease_token: str | None = None
) -> str:
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT state, owner, lease_until, lease_token FROM slices WHERE id=?", (slice_id,)
    ).fetchone()
    if row is None:
        db.commit()
        return "not_found"
    if lease_token is not None and row["lease_token"] != lease_token:
        db.commit()
        return "lease_invalid"
    if row["state"] == "done":
        db.commit()
        return "already_done"
    if row["state"] != "leased" or row["owner"] != node_id or row["lease_until"] <= now:
        db.commit()
        return "lease_invalid"
    db.execute("UPDATE slices SET state='done', lease_until=NULL WHERE id=?", (slice_id,))
    db.commit()
    return "done"


def renew(
    db: sqlite3.Connection,
    slice_id: int,
    node_id: str,
    lease_seconds: int = 120,
    lease_token: str | None = None,
) -> str:
    """仅允许当前有效租约的持有者续期，不复活过期任务。"""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT state, owner, lease_until, lease_token FROM slices WHERE id=?", (slice_id,)
    ).fetchone()
    if row is None:
        db.commit()
        return "not_found"
    if (
        row["state"] != "leased"
        or row["owner"] != node_id
        or row["lease_until"] <= now
        or (lease_token is not None and row["lease_token"] != lease_token)
    ):
        db.commit()
        return "lease_invalid"
    db.execute(
        "UPDATE slices SET lease_until=? WHERE id=?",
        (max(now + lease_seconds, row["lease_until"]), slice_id),
    )
    db.commit()
    return "renewed"

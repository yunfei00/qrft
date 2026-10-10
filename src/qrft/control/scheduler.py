"""SQLite 原子时间片租约调度：超时回收、重复领取保护、完成幂等。"""

from __future__ import annotations

import sqlite3
import time


def init_schema(db: sqlite3.Connection) -> None:
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


def claim(db: sqlite3.Connection, node_id: str, lease_seconds: int = 120) -> dict | None:
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        """
        SELECT s.id, s.video_id, s.start_ms, s.end_ms, v.path, s.attempts
        FROM slices s JOIN videos v ON v.id=s.video_id
        WHERE s.state='pending' OR (s.state='leased' AND s.lease_until <= ?)
        ORDER BY s.id LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        db.commit()
        return None
    db.execute(
        "UPDATE slices SET state='leased', owner=?, lease_until=?, attempts=attempts+1 WHERE id=?",
        (node_id, now + lease_seconds, row["id"]),
    )
    db.commit()
    return {**dict(row), "owner": node_id, "lease_until": now + lease_seconds}


def complete(db: sqlite3.Connection, slice_id: int, node_id: str) -> str:
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT state, owner, lease_until FROM slices WHERE id=?", (slice_id,)
    ).fetchone()
    if row is None:
        db.commit()
        return "not_found"
    if row["state"] == "done":
        db.commit()
        return "already_done"
    if row["state"] != "leased" or row["owner"] != node_id or row["lease_until"] <= now:
        db.commit()
        return "lease_invalid"
    db.execute("UPDATE slices SET state='done', lease_until=NULL WHERE id=?", (slice_id,))
    db.commit()
    return "done"


def renew(db: sqlite3.Connection, slice_id: int, node_id: str, lease_seconds: int = 120) -> str:
    """仅允许当前有效租约的持有者续期，不复活过期任务。"""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    now = time.time()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT state, owner, lease_until FROM slices WHERE id=?", (slice_id,)
    ).fetchone()
    if row is None:
        db.commit()
        return "not_found"
    if row["state"] != "leased" or row["owner"] != node_id or row["lease_until"] <= now:
        db.commit()
        return "lease_invalid"
    db.execute(
        "UPDATE slices SET lease_until=? WHERE id=?",
        (max(now, row["lease_until"]) + lease_seconds, slice_id),
    )
    db.commit()
    return "renewed"

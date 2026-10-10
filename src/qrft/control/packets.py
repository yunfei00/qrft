"""持久化二维码原始帧，隔离同 ID 冲突，不信任客户端提供的校验结果。"""

from __future__ import annotations

import hashlib
import sqlite3
import time

from qrft.core.protocol import Frame, ProtocolError, decode_frame


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS packets (
            task_id INTEGER NOT NULL,
            packet_id INTEGER NOT NULL,
            frame BLOB NOT NULL,
            digest TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY(task_id, packet_id)
        );
        CREATE TABLE IF NOT EXISTS packet_conflicts (
            task_id INTEGER NOT NULL,
            packet_id INTEGER NOT NULL,
            digest TEXT NOT NULL,
            frame BLOB NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY(task_id, packet_id, digest)
        );
        """
    )


def ingest(db: sqlite3.Connection, task_id: int, raw: bytes) -> str:
    """返回 inserted / duplicate / conflict；CRC 和格式由协议解码器验证。"""
    frame: Frame = decode_frame(raw)
    if frame.kind != "data":
        raise ProtocolError("only DATA frames accepted by packet ingestion")
    digest = hashlib.sha256(raw).hexdigest()
    db.execute("SAVEPOINT qrft_packet_ingest")
    existing = db.execute(
        "SELECT digest FROM packets WHERE task_id=? AND packet_id=?",
        (task_id, frame.packet_id),
    ).fetchone()
    if existing is None:
        db.execute(
            "INSERT INTO packets(task_id,packet_id,frame,digest,created_at) VALUES (?,?,?,?,?)",
            (task_id, frame.packet_id, raw, digest, time.time()),
        )
        db.execute("RELEASE SAVEPOINT qrft_packet_ingest")
        return "inserted"
    if existing["digest"] == digest:
        db.execute("RELEASE SAVEPOINT qrft_packet_ingest")
        return "duplicate"
    db.execute(
        "INSERT OR IGNORE INTO packet_conflicts "
        "(task_id,packet_id,digest,frame,created_at) VALUES (?,?,?,?,?)",
        (task_id, frame.packet_id, digest, raw, time.time()),
    )
    db.execute("RELEASE SAVEPOINT qrft_packet_ingest")
    return "conflict"

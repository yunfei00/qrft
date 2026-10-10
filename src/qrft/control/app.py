"""QRFT 控制中心：SQLite 持久化任务、视频登记与节点心跳。"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from qrft.control.packets import ingest
from qrft.control.packets import init_schema as init_packets
from qrft.control.recovery import recover
from qrft.control.scheduler import add_slices, claim, complete, init_schema, renew
from qrft.control.web import PAGE
from qrft.core.missing import export_missing
from qrft.core.protocol import ProtocolError, decode_frame

app = FastAPI(title="QRFT Control", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
def management() -> HTMLResponse:
    # Public login shell contains no task, node, path or token data.
    return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})


def database_path() -> Path:
    return Path(os.environ.get("QRFT_DB_PATH", "qrft-control.sqlite3"))


@contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                path TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                last_seen REAL NOT NULL
            );
            """
        )
        init_schema(db)
        init_packets(db)
        db.execute("CREATE TABLE IF NOT EXISTS task_finishes (task_id INTEGER PRIMARY KEY)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS task_recoveries (task_id INTEGER PRIMARY KEY, "
            "status TEXT NOT NULL, path TEXT, updated_at REAL NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS task_manifests ("
            "task_id INTEGER PRIMARY KEY, start_frame BLOB NOT NULL, "
            "total_packets INTEGER NOT NULL, chunk_size INTEGER NOT NULL, "
            "file_size INTEGER NOT NULL)"
        )
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
    finally:
        db.close()


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("QRFT_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="QRFT_API_TOKEN is not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid API token")


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class VideoCreate(BaseModel):
    task_id: int = Field(gt=0)
    path: str = Field(min_length=1, max_length=4096)
    duration_seconds: float = Field(gt=0)


class SliceClaim(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=120, ge=1, le=3600)


class SliceRenew(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=120, ge=1, le=3600)


class ManifestBind(BaseModel):
    task_id: int = Field(gt=0)
    start_base64: str


class PacketBatch(BaseModel):
    task_id: int = Field(gt=0)
    frames_base64: list[str] = Field(min_length=1, max_length=1000)


class SliceComplete(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)


class Heartbeat(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks", dependencies=[Depends(require_token)], status_code=201)
def create_task(item: TaskCreate) -> dict[str, int]:
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO tasks(name, created_at) VALUES (?, ?)", (item.name, time.time())
        )
        return {"id": int(cursor.lastrowid)}


@app.get("/tasks", dependencies=[Depends(require_token)])
def list_tasks() -> list[dict]:
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM tasks ORDER BY id DESC")]


@app.post("/videos", dependencies=[Depends(require_token)], status_code=201)
def register_video(item: VideoCreate) -> dict[str, int]:
    with connection() as db:
        if db.execute("SELECT 1 FROM tasks WHERE id = ?", (item.task_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Task not found")
        cursor = db.execute(
            "INSERT INTO videos(task_id, path, duration_seconds, created_at) VALUES (?, ?, ?, ?)",
            (item.task_id, item.path, item.duration_seconds, time.time()),
        )
        video_id = int(cursor.lastrowid)
        add_slices(db, video_id, item.duration_seconds)
        return {"id": video_id}


@app.get("/videos", dependencies=[Depends(require_token)])
def list_videos(task_id: int | None = None) -> list[dict]:
    with connection() as db:
        if task_id is None:
            rows = db.execute("SELECT * FROM videos ORDER BY id DESC")
        else:
            rows = db.execute("SELECT * FROM videos WHERE task_id = ? ORDER BY id DESC", (task_id,))
        return [dict(row) for row in rows]


@app.post("/nodes/heartbeat", dependencies=[Depends(require_token)])
def heartbeat(item: Heartbeat) -> dict[str, str]:
    with connection() as db:
        db.execute(
            "INSERT INTO nodes(node_id, last_seen) VALUES (?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET last_seen = excluded.last_seen",
            (item.node_id, time.time()),
        )
    return {"status": "ok"}


@app.get("/nodes", dependencies=[Depends(require_token)])
def list_nodes() -> list[dict]:
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM nodes ORDER BY node_id")]


@app.post("/slices/claim", dependencies=[Depends(require_token)])
def claim_slice(item: SliceClaim) -> dict | None:
    with connection() as db:
        return claim(db, item.node_id, item.lease_seconds)


@app.post("/slices/{slice_id}/complete", dependencies=[Depends(require_token)])
def complete_slice(slice_id: int, item: SliceComplete) -> dict[str, str]:
    with connection() as db:
        result = complete(db, slice_id, item.node_id)
        if result == "not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "lease_invalid":
            raise HTTPException(status_code=409, detail=result)
        return {"status": result}


@app.get("/slices", dependencies=[Depends(require_token)])
def list_slices(video_id: int | None = None) -> list[dict]:
    with connection() as db:
        if video_id is None:
            rows = db.execute("SELECT * FROM slices ORDER BY id")
        else:
            rows = db.execute("SELECT * FROM slices WHERE video_id=? ORDER BY id", (video_id,))
        return [dict(row) for row in rows]


@app.post("/slices/{slice_id}/renew", dependencies=[Depends(require_token)])
def renew_slice(slice_id: int, item: SliceRenew) -> dict[str, str]:
    with connection() as db:
        result = renew(db, slice_id, item.node_id, item.lease_seconds)
        if result == "not_found":
            raise HTTPException(status_code=404, detail=result)
        if result == "lease_invalid":
            raise HTTPException(status_code=409, detail=result)
        return {"status": result}


@app.post("/tasks/manifest", dependencies=[Depends(require_token)])
def bind_manifest(item: ManifestBind) -> dict[str, str]:
    try:
        raw = base64.b64decode(item.start_base64, validate=True)
        if len(raw) > 8192:
            raise ValueError("START frame exceeds size limit")
        frame = decode_frame(raw)
        if frame.kind != "start" or frame.metadata is None:
            raise ProtocolError("START frame required")
        meta = frame.metadata
        size, chunk, total = (meta.get(k) for k in ("file_size", "chunk_size", "total_packets"))
        if (
            type(size) is not int
            or type(chunk) is not int
            or type(total) is not int
            or size < 0
            or chunk <= 0
            or total != (size + chunk - 1) // chunk
            or total > 88888888
        ):
            raise ProtocolError("invalid START manifest sizes")
        if not all(
            isinstance(meta.get(key), str)
            and len(meta[key]) == length
            and all(ch in "0123456789abcdefABCDEF" for ch in meta[key])
            for key, length in (("sha256", 64), ("md5", 32))
        ):
            raise ProtocolError("invalid manifest hashes")
    except (ValueError, binascii.Error, ProtocolError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM tasks WHERE id=?", (item.task_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Task not found")
        existing = db.execute(
            "SELECT start_frame FROM task_manifests WHERE task_id=?", (item.task_id,)
        ).fetchone()
        if existing is not None:
            if existing["start_frame"] != raw:
                raise HTTPException(status_code=409, detail="Conflicting START manifest")
            return {"status": "already_bound"}
        for row in db.execute("SELECT frame FROM packets WHERE task_id=?", (item.task_id,)):
            data = decode_frame(bytes(row["frame"]))
            if data.packet_id >= total or len(data.payload) != min(
                chunk, size - data.packet_id * chunk
            ):
                raise HTTPException(status_code=409, detail="Stored DATA does not match START")
        db.execute(
            "INSERT INTO task_manifests(task_id,start_frame,total_packets,chunk_size,file_size) "
            "VALUES (?,?,?,?,?)",
            (item.task_id, raw, total, chunk, size),
        )
    return {"status": "bound"}


@app.get("/tasks/{task_id}/missing", dependencies=[Depends(require_token)])
def missing_packets(task_id: int) -> dict:
    with connection() as db:
        manifest = db.execute(
            "SELECT total_packets FROM task_manifests WHERE task_id=?", (task_id,)
        ).fetchone()
        if manifest is None:
            raise HTTPException(status_code=404, detail="START manifest not bound")
        received = {
            row[0]
            for row in db.execute("SELECT packet_id FROM packets WHERE task_id=?", (task_id,))
        }
        total = manifest["total_packets"]
        missing = [packet_id for packet_id in range(total) if packet_id not in received]
        return {"total_packets": total, "received": len(received), "missing_ids": missing}


@app.post("/packets/batch", dependencies=[Depends(require_token)])
def ingest_batch(item: PacketBatch) -> dict[str, int]:
    counts = {"inserted": 0, "duplicate": 0, "conflict": 0}
    with connection() as db:
        if db.execute("SELECT 1 FROM tasks WHERE id=?", (item.task_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Task not found")
        db.execute("BEGIN IMMEDIATE")
        for encoded in item.frames_base64:
            try:
                raw = base64.b64decode(encoded, validate=True)
                if len(raw) > 8192:
                    raise ValueError("frame exceeds size limit")
                frame = decode_frame(raw)
                if frame.kind == "finish":
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO task_finishes VALUES (?)", (item.task_id,)
                    )
                    counts["inserted" if cursor.rowcount else "duplicate"] += 1
                    continue
                manifest = db.execute(
                    "SELECT total_packets,chunk_size,file_size FROM task_manifests WHERE task_id=?",
                    (item.task_id,),
                ).fetchone()
                if manifest is not None and (
                    frame.kind != "data"
                    or frame.packet_id >= manifest["total_packets"]
                    or len(frame.payload)
                    != min(
                        manifest["chunk_size"],
                        manifest["file_size"] - frame.packet_id * manifest["chunk_size"],
                    )
                ):
                    raise ProtocolError("DATA frame does not match bound manifest")
                result = ingest(db, item.task_id, raw)
            except (ValueError, binascii.Error, ProtocolError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            counts[result] += 1
    return counts


@app.get("/packets/{task_id}/stats", dependencies=[Depends(require_token)])
def packet_stats(task_id: int) -> dict[str, int]:
    with connection() as db:
        stored = db.execute("SELECT COUNT(*) FROM packets WHERE task_id=?", (task_id,)).fetchone()[
            0
        ]
        conflicts = db.execute(
            "SELECT COUNT(*) FROM packet_conflicts WHERE task_id=?", (task_id,)
        ).fetchone()[0]
    return {"stored": stored, "conflicts": conflicts}


@app.get("/tasks/{task_id}/progress", dependencies=[Depends(require_token)])
def task_progress(task_id: int) -> dict:
    stats = packet_stats(task_id)
    with connection() as db:
        if db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Task not found")
        stats["finished"] = (
            db.execute("SELECT 1 FROM task_finishes WHERE task_id=?", (task_id,)).fetchone()
            is not None
        )
        recovery = db.execute(
            "SELECT status,path,updated_at FROM task_recoveries WHERE task_id=?", (task_id,)
        ).fetchone()
        stats["recovery"] = dict(recovery) if recovery else {"status": "not_started"}
        stats["slices"] = [
            dict(row)
            for row in db.execute(
                "SELECT s.state, COUNT(*) AS count FROM slices s JOIN videos v ON v.id=s.video_id "
                "WHERE v.task_id=? GROUP BY s.state",
                (task_id,),
            )
        ]
    try:
        stats.update(missing_packets(task_id))
    except HTTPException:
        stats["total_packets"] = None
    return stats


@app.post("/tasks/{task_id}/missing/export", dependencies=[Depends(require_token)])
def export_task_missing(task_id: int) -> dict:
    missing = missing_packets(task_id)
    directory = Path(os.environ.get("QRFT_OUTPUT_DIR", "recovered")) / str(task_id)
    with connection() as db:
        received = (
            row[0]
            for row in db.execute("SELECT packet_id FROM packets WHERE task_id=?", (task_id,))
        )
        export_missing(directory, missing["total_packets"], received)
    return {"directory": str(directory), **missing}


@app.post("/tasks/{task_id}/recover", dependencies=[Depends(require_token)])
def recover_task(task_id: int) -> dict:
    directory = Path(os.environ.get("QRFT_OUTPUT_DIR", "recovered")) / str(task_id)
    with connection() as db:
        db.execute("BEGIN")
        try:
            result = recover(db, task_id, directory)
        except (ProtocolError, FileExistsError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    with connection() as db:
        db.execute(
            "INSERT INTO task_recoveries VALUES (?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET status=excluded.status, "
            "path=excluded.path,updated_at=excluded.updated_at",
            (task_id, result["status"], result.get("path"), time.time()),
        )
    return result


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="QRFT Control")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args(argv)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

"""QRFT 控制中心：SQLite 持久化任务、视频登记与节点心跳。"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from qrft.control.scheduler import add_slices, claim, complete, init_schema

app = FastAPI(title="QRFT Control", version="0.1.0")


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
        yield db
        db.commit()
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


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)


if __name__ == "__main__":
    main()

"""控制中心的 SQLite 持久化和 API 鉴权回归测试。"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from qrft.control.app import app  # noqa: E402


def test_health_and_token_required(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.delenv("QRFT_API_TOKEN", raising=False)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/tasks").status_code == 503
    monkeypatch.setenv("QRFT_API_TOKEN", "test-secret")
    assert client.get("/tasks").status_code == 401


def test_registry_persists_and_heartbeat_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "test-secret")
    headers = {"Authorization": "Bearer test-secret"}
    client = TestClient(app)
    task = client.post("/tasks", json={"name": "video-001"}, headers=headers)
    assert task.status_code == 201
    task_id = task.json()["id"]
    assert client.post(
        "/videos",
        json={"task_id": 9999, "path": "missing.avi", "duration_seconds": 10},
        headers=headers,
    ).status_code == 404
    video = client.post(
        "/videos",
        json={"task_id": task_id, "path": r"\\server\share\sample.avi", "duration_seconds": 10},
        headers=headers,
    )
    assert video.status_code == 201
    for _ in range(2):
        assert client.post(
            "/nodes/heartbeat", json={"node_id": "worker-a"}, headers=headers
        ).status_code == 200
    assert len(client.get("/nodes", headers=headers).json()) == 1
    assert len(client.get("/videos", headers=headers).json()) == 1
    assert len(client.get("/tasks", headers=headers).json()) == 1
    assert len(TestClient(app).get("/tasks", headers=headers).json()) == 1

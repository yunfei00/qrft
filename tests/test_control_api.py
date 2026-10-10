"""控制中心的 SQLite 持久化和 API 鉴权回归测试。"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from qrft.control.app import app


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
    assert (
        client.post(
            "/videos",
            json={"task_id": 9999, "path": "missing.avi", "duration_seconds": 10},
            headers=headers,
        ).status_code
        == 404
    )
    video = client.post(
        "/videos",
        json={"task_id": task_id, "path": r"\\server\share\sample.avi", "duration_seconds": 10},
        headers=headers,
    )
    assert video.status_code == 201
    for _ in range(2):
        assert (
            client.post(
                "/nodes/heartbeat", json={"node_id": "worker-a"}, headers=headers
            ).status_code
            == 200
        )
    assert len(client.get("/nodes", headers=headers).json()) == 1
    assert len(client.get("/videos", headers=headers).json()) == 1
    assert len(client.get("/tasks", headers=headers).json()) == 1
    assert len(TestClient(app).get("/tasks", headers=headers).json()) == 1


def test_manifest_missing_and_atomic_batch(tmp_path, monkeypatch) -> None:
    import base64

    from qrft.core.protocol import encode_data, encode_start

    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "batch.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "test-secret")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret"}
    task_id = client.post("/tasks", json={"name": "binary"}, headers=headers).json()["id"]
    manifest = {
        "file_size": 5,
        "chunk_size": 3,
        "total_packets": 2,
        "sha256": "a" * 64,
        "md5": "b" * 32,
    }
    start = base64.b64encode(encode_start(manifest)).decode("ascii")
    bound = client.post(
        "/tasks/manifest",
        json={"task_id": task_id, "start_base64": start},
        headers=headers,
    )
    assert bound.status_code == 200
    assert bound.json()["status"] == "bound"
    assert client.get(f"/tasks/{task_id}/missing", headers=headers).json()["missing_ids"] == [0, 1]
    first = base64.b64encode(encode_data(0, b"abc")).decode("ascii")
    invalid = base64.b64encode(encode_data(1, b"wrong")).decode("ascii")
    rejected = client.post(
        "/packets/batch",
        json={"task_id": task_id, "frames_base64": [first, invalid]},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert client.get(f"/packets/{task_id}/stats", headers=headers).json()["stored"] == 0
    second = base64.b64encode(encode_data(1, b"de")).decode("ascii")
    accepted = client.post(
        "/packets/batch",
        json={"task_id": task_id, "frames_base64": [first, second]},
        headers=headers,
    )
    assert accepted.json()["inserted"] == 2
    assert client.get(f"/tasks/{task_id}/missing", headers=headers).json()["missing_ids"] == []

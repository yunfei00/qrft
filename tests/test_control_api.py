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


def test_control_uses_v2_and_keeps_management_page(tmp_path, monkeypatch):
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "test-secret")
    headers = {"Authorization": "Bearer test-secret"}
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert "QRFT 控制中心" in page.text
    assert 'id="protocol"' not in page.text
    assert client.get("/settings", headers=headers).json()["protocol_version"] == 2
    task = client.post("/tasks", json={"name": "v2-default"}, headers=headers).json()["id"]
    assert client.get(f"/tasks/{task}/progress", headers=headers).json()["protocol_version"] == 2
    for version in (1, 3):
        assert (
            client.post(
                "/tasks", json={"name": "unsupported", "protocol_version": version}, headers=headers
            ).status_code
            == 422
        )


@pytest.mark.parametrize("with_protocol_table", [False, True])
def test_legacy_database_requires_new_v2_database(tmp_path, monkeypatch, with_protocol_table):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,name TEXT,created_at REAL)")
        db.execute("INSERT INTO tasks VALUES (1,'old',0)")
        if with_protocol_table:
            db.execute("CREATE TABLE task_protocols(task_id INTEGER PRIMARY KEY,version INTEGER)")
            db.execute("INSERT INTO task_protocols VALUES (1,1)")
    monkeypatch.setenv("QRFT_DB_PATH", str(path))
    monkeypatch.setenv("QRFT_API_TOKEN", "test-secret")
    response = TestClient(app).get("/tasks", headers={"Authorization": "Bearer test-secret"})
    assert response.status_code == 409
    assert "v2" in response.json()["detail"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM tasks").fetchall() == [("old",)]


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
        "version": 2,
        "filename": "sample.bin",
        "file_size": None,
        "chunk_size": 3,
        "total_packets": 2,
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


@pytest.mark.parametrize("valid_fingerprint", [False, True])
def test_folder_fingerprint_checked_before_publication(tmp_path, monkeypatch, valid_fingerprint):
    import base64
    import json
    from io import BytesIO
    from pathlib import Path
    from zipfile import ZipFile

    from qrft.core.protocol import encode_start
    from qrft.encoder_cli.archive import FORMAT
    from qrft.encoder_cli.source import Source

    if valid_fingerprint:
        source_path = tmp_path / "source-folder"
        (source_path / "empty").mkdir(parents=True)
        (source_path / "content.bin").write_bytes(b"folder file content")
    else:
        data = BytesIO()
        with ZipFile(data, "w") as zipped:
            zipped.writestr("some.bin", b"data")
            zipped.comment = json.dumps(
                {
                    "format": FORMAT,
                    "folder_content_md5": "0" * 32,
                    "folder_content_sha256": "0" * 64,
                }
            ).encode()
        source_path = tmp_path / "bad-folder.zip"
        source_path.write_bytes(data.getvalue())
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("QRFT_API_TOKEN", "test-secret")
    client = TestClient(app, headers={"Authorization": "Bearer test-secret"})
    task = client.post("/tasks", json={"name": "folder"}).json()["id"]
    with Source(source_path, chunk_size=64) as source:
        start = base64.b64encode(encode_start(source.metadata)).decode()
        assert (
            client.post(
                "/tasks/manifest", json={"task_id": task, "start_base64": start}
            ).status_code
            == 200
        )
        frames = [
            base64.b64encode(raw).decode() for name, raw in source.frames() if name != "START"
        ]
        assert (
            client.post(
                "/packets/batch", json={"task_id": task, "frames_base64": frames}
            ).status_code
            == 200
        )
        response = client.post(f"/tasks/{task}/recover")
        if valid_fingerprint:
            assert response.status_code == 200
            result = response.json()
            assert result["folder"]["status"] == "PASS"
            assert result["folder"]["auto_extracted"] is False
            assert (
                result["folder"]["folder_content_md5"]
                == source.archive_details["folder_content_md5"]
            )
            with source.open_stream() as expected:
                assert Path(result["path"]).read_bytes() == expected.read()
        else:
            assert response.status_code == 409
            assert "fingerprint mismatch" in response.json()["detail"]
            assert not list((tmp_path / "output" / str(task)).rglob("bad-folder.zip"))

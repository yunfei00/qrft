import json
import tracemalloc
from itertools import islice

import pytest
from fastapi.testclient import TestClient

from qrft.control.app import app
from qrft.core.missing import iter_missing, stream_missing
from qrft.core.protocol import ProtocolError


def test_paginated_download_and_cancel(tmp_path, monkeypatch):
    import base64

    from qrft.core.manifest import inspect_file
    from qrft.core.protocol import encode_data, encode_start

    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "secret")
    client = TestClient(app, headers={"Authorization": "Bearer secret"})
    task = client.post("/tasks", json={"name": "分页"}).json()["id"]
    source = tmp_path / "中文.bin"
    source.write_bytes(b"abcdef")
    assert (
        client.post(
            "/tasks/manifest",
            json={
                "task_id": task,
                "start_base64": base64.b64encode(encode_start(inspect_file(source, 1))).decode(),
            },
        ).status_code
        == 200
    )
    page = client.get(f"/tasks/{task}/missing?limit=2").json()
    assert page["missing_ids"] == [0, 1]
    assert page["missing_count"] == 6
    assert page["next_after"] == 1
    assert client.get(f"/tasks/{task}/missing?limit=2&after=1").json()["missing_ids"] == [2, 3]
    downloaded = client.get(f"/tasks/{task}/missing/download?format=json")
    assert downloaded.json()["missing_ids"] == list(range(6))
    assert "secret" not in downloaded.text
    client.post("/videos", json={"task_id": task, "path": "test.avi", "duration_seconds": 5})
    assert client.post(f"/tasks/{task}/cancel").status_code == 200
    assert client.post("/slices/claim", json={"node_id": "node"}).json() is None
    assert (
        client.post(
            "/packets/batch",
            json={
                "task_id": task,
                "frames_base64": [base64.b64encode(encode_data(0, b"a")).decode()],
            },
        ).status_code
        == 409
    )


def test_large_missing_is_bounded():
    tracemalloc.start()
    assert list(islice(iter_missing(88_888_888, []), 10)) == list(range(10))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 100_000


def test_stream_reports_and_validation(tmp_path):
    assert stream_missing(tmp_path, 6, iter([1, 3, 5])) == 3
    assert (tmp_path / "missing.txt").read_text() == "00000000\n00000002\n00000004\n"
    assert json.loads((tmp_path / "missing.json").read_text())["missing_ids"] == [0, 2, 4]
    with pytest.raises(ProtocolError):
        list(iter_missing(4, [2, 1]))


def test_download_requires_token_and_valid_format(tmp_path, monkeypatch):
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "secret")
    client = TestClient(app)
    assert client.get("/tasks/1/missing/download").status_code == 401
    assert (
        client.get(
            "/tasks/1/missing/download?format=exe", headers={"Authorization": "Bearer secret"}
        ).status_code
        == 422
    )

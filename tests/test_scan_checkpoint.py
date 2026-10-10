import base64

from fastapi.testclient import TestClient

from qrft.control.app import app, connection
from qrft.core.protocol import encode_data


def test_checkpoint_reassignment_fences_same_node(tmp_path, monkeypatch):
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "secret")
    client = TestClient(app, headers={"Authorization": "Bearer secret"})
    task = client.post("/tasks", json={"name": "checkpoint"}).json()["id"]
    client.post("/videos", json={"task_id": task, "path": "video.avi", "duration_seconds": 10})
    lease = client.post("/slices/claim", json={"node_id": "node"}).json()
    checkpoint = {"node_id": "node", "lease_token": lease["lease_token"], "checkpoint_ms": 6000}
    assert client.post(f"/slices/{lease['id']}/checkpoint", json=checkpoint).status_code == 200
    assert (
        client.post(
            f"/slices/{lease['id']}/checkpoint", json={**checkpoint, "checkpoint_ms": 11000}
        ).status_code
        == 422
    )
    with connection() as db:
        db.execute("UPDATE slices SET lease_until=0 WHERE id=?", (lease["id"],))
    renewed = client.post("/slices/claim", json={"node_id": "node"}).json()
    assert renewed["checkpoint_ms"] == 6000
    assert renewed["lease_token"] != lease["lease_token"]
    assert client.post(f"/slices/{lease['id']}/checkpoint", json=checkpoint).status_code == 409
    stale = {"node_id": "node", "lease_token": lease["lease_token"]}
    assert client.post(f"/slices/{lease['id']}/renew", json=stale).status_code == 409
    assert client.post(f"/slices/{lease['id']}/complete", json=stale).status_code == 409
    data = {
        "task_id": task,
        "slice_id": lease["id"],
        "lease_token": lease["lease_token"],
        "frames_base64": [base64.b64encode(encode_data(0, b"a")).decode()],
    }
    assert client.post("/packets/batch", json=data).status_code == 409
    assert (
        client.post(
            "/packets/batch", json={**data, "lease_token": renewed["lease_token"]}
        ).status_code
        == 200
    )


def test_worker_flushes_before_checkpoint_and_replays_overlap(monkeypatch):
    from qrft.core.protocol import Frame
    from qrft.decoder import worker

    calls = []
    clock = iter([0, 6, 6])
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        worker, "request_json", lambda base, token, route, payload: calls.append((route, payload))
    )

    def frames(path, **options):
        assert options["start_seconds"] == 5
        yield Frame("data", 0, b"abc")
        options["on_sample"](7000)

    monkeypatch.setattr(worker, "iter_video_frames", frames)
    lease = {
        "id": 1,
        "task_id": 1,
        "path": "video.avi",
        "start_ms": 0,
        "end_ms": 10000,
        "checkpoint_ms": 6000,
        "lease_token": "generation",
    }
    worker.process_slice("http://localhost", "secret", "node", lease)
    assert [route for route, _ in calls] == [
        "/packets/batch",
        "/slices/1/checkpoint",
        "/slices/1/complete",
    ]
    assert calls[0][1]["lease_token"] == "generation"

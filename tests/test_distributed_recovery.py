"""Distributed ordering, retransmission and durable recovery regression tests."""

import base64
import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from qrft.control.app import app
from qrft.core.manifest import inspect_file, parse_packet_list
from qrft.core.protocol import encode_data, encode_finish, encode_start


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("QRFT_API_TOKEN", "test-token")
    return TestClient(app, headers={"Authorization": "Bearer test-token"})


def submit(client, task, frames):
    return client.post(
        "/packets/batch",
        json={
            "task_id": task,
            "frames_base64": [base64.b64encode(raw).decode("ascii") for raw in frames],
        },
    )


def bind(client, task, meta):
    return client.post(
        "/tasks/manifest",
        json={
            "task_id": task,
            "start_base64": base64.b64encode(encode_start(meta)).decode("ascii"),
        },
    )


@pytest.mark.parametrize("content", [b"", bytes(range(256)) * 3], ids=["empty", "binary"])
@pytest.mark.parametrize(
    "filename", ["all-bytes.bin", "missing.txt", "received.part", "no-extension"]
)
def test_data_before_start_retransmission_and_restart(control, tmp_path, content, filename):
    source = tmp_path / filename
    source.write_bytes(content)
    meta = inspect_file(source, 64)
    task = control.post("/tasks", json={"name": "binary"}).json()["id"]
    frames = [encode_data(i, content[i * 64 : (i + 1) * 64]) for i in range(meta["total_packets"])]
    # The later slice, with FINISH but no START, reaches the server first.
    assert submit(control, task, [*reversed(frames[1:]), encode_finish()]).status_code == 200
    assert bind(control, task, meta).status_code == 200
    assert bind(control, task, meta).json()["status"] == "already_bound"
    exported = control.post(f"/tasks/{task}/missing/export").json()
    missing = parse_packet_list(
        (Path(exported["directory"]) / "missing.txt").read_text(), len(frames)
    )
    assert missing == ([0] if frames else [])
    assert control.post(f"/tasks/{task}/recover").json()["status"] == (
        "incomplete" if frames else "verified"
    )
    if frames:
        assert submit(control, task, [frames[0], frames[0]]).json()["duplicate"] == 1
        restarted = TestClient(app, headers={"Authorization": "Bearer test-token"})
        result = restarted.post(f"/tasks/{task}/recover").json()
        assert result["status"] == "verified"
        assert Path(result["path"]).read_bytes() == content
        assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert control.post(f"/tasks/{task}/recover").status_code == 409
    assert control.get(f"/tasks/{task}/progress").json()["finished"] is True


def test_conflicting_start_and_bad_preexisting_packet(control, tmp_path):
    source = tmp_path / "sample.bin"
    source.write_bytes(b"abc")
    meta = inspect_file(source, 3)
    task = control.post("/tasks", json={"name": "binary"}).json()["id"]
    assert submit(control, task, [encode_data(0, b"incorrect")]).status_code == 200
    assert bind(control, task, meta).status_code == 409


def test_hash_failure_does_not_publish(control, tmp_path):
    source = tmp_path / "sample.bin"
    source.write_bytes(b"abc")
    task = control.post("/tasks", json={"name": "binary"}).json()["id"]
    assert bind(control, task, inspect_file(source, 3)).status_code == 200
    assert submit(control, task, [encode_data(0, b"xyz"), encode_finish()]).status_code == 200
    assert control.post(f"/tasks/{task}/recover").status_code == 409
    assert not (tmp_path / "output" / str(task) / "files" / source.name).exists()


@pytest.mark.parametrize("workers", [1, 2])
def test_workers_real_avi(control, tmp_path, monkeypatch, workers):
    pytest.importorskip("cv2")
    pytest.importorskip("zxingcpp")
    from qrft.decoder import worker
    from qrft.encoder_cli.video_export import export_video

    source = tmp_path / "payload.bin"
    source.write_bytes(bytes(range(256)))
    video = export_video(source, tmp_path / "recording.avi", chunk_size=64)
    # Twenty START, four DATA, twenty FINISH frames at 20 fps.
    duration = 44 / 20
    task = control.post("/tasks", json={"name": "AVI"}).json()["id"]
    video_id = control.post(
        "/videos", json={"task_id": task, "path": str(video), "duration_seconds": duration}
    ).json()["id"]

    def request(base_url, token, route, payload):
        response = control.post(route, json=payload)
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(worker, "request_json", request)
    if workers == 1:
        worker.run_worker("http://localhost", "test-token", "a", once=True)
    else:
        from qrft.control.app import connection

        with connection() as db:
            db.execute("DELETE FROM slices WHERE video_id=?", (video_id,))
            db.executemany(
                "INSERT INTO slices(video_id,start_ms,end_ms) VALUES (?,?,?)",
                [(video_id, 0, 1100), (video_id, 1100, 2200)],
            )
        first = request("", "", "/slices/claim", {"node_id": "a"})
        second = request("", "", "/slices/claim", {"node_id": "b"})
        # The slice without START is processed before the first node.
        worker.process_slice("http://localhost", "test-token", "b", second, sample_fps=60)
        worker.process_slice("http://localhost", "test-token", "a", first, sample_fps=60)
    result = control.post(f"/tasks/{task}/recover").json()
    assert result["status"] == "verified"
    assert Path(result["path"]).read_bytes() == source.read_bytes()


def test_unreadable_qr_in_real_video_and_retransmission(control, tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("zxingcpp")
    from qrft.decoder import worker
    from qrft.encoder_cli.video_export import export_video

    source = tmp_path / "binary.bin"
    source.write_bytes(bytes(range(256)))
    good = export_video(source, tmp_path / "good.avi", chunk_size=64)
    damaged = tmp_path / "damaged.avi"
    reader = cv2.VideoCapture(str(good))
    width = int(reader.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(damaged), cv2.VideoWriter_fourcc(*"MJPG"), 20, (width, height))
    assert writer.isOpened()
    try:
        index = 0
        while True:
            ok, image = reader.read()
            if not ok:
                break
            if index == 21:
                image[:] = 255  # Remove DATA 1.
            writer.write(image)
            index += 1
    finally:
        reader.release()
        writer.release()
    task = control.post("/tasks", json={"name": "damaged"}).json()["id"]
    control.post("/videos", json={"task_id": task, "path": str(damaged), "duration_seconds": 2.2})

    def request(base_url, token, route, payload):
        response = control.post(route, json=payload)
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(worker, "request_json", request)
    worker.run_worker("http://localhost", "test-token", "a", once=True)
    assert control.get(f"/tasks/{task}/missing").json()["missing_ids"] == [1]
    assert control.post(f"/tasks/{task}/recover").json()["status"] == "incomplete"
    control.post("/videos", json={"task_id": task, "path": str(good), "duration_seconds": 2.2})
    worker.run_worker("http://localhost", "test-token", "b", once=True)
    result = control.post(f"/tasks/{task}/recover").json()
    assert result["status"] == "verified"
    assert Path(result["path"]).read_bytes() == source.read_bytes()


def test_new_operations_require_token(control):
    unauthenticated = TestClient(app)
    for method, path in (
        ("get", "/tasks/1/progress"),
        ("post", "/tasks/1/recover"),
        ("post", "/tasks/1/missing/export"),
    ):
        assert getattr(unauthenticated, method)(path).status_code == 401
    page = unauthenticated.get("/")
    assert page.status_code == 200
    assert "Bearer " in page.text
    assert "localStorage" not in page.text
    assert "test-token" not in page.text


def test_finish_batch_rollback_and_manifest_conflict(control, tmp_path):
    source = tmp_path / "sample.bin"
    source.write_bytes(b"abc")
    meta = inspect_file(source, 3)
    task = control.post("/tasks", json={"name": "binary"}).json()["id"]
    assert bind(control, task, meta).status_code == 200
    changed = {**meta, "md5": "0" * 32}
    assert bind(control, task, changed).status_code == 409
    assert submit(control, task, [encode_finish(), b"bad"]).status_code == 422
    assert control.get(f"/tasks/{task}/progress").json()["finished"] is False


def test_same_node_cannot_accumulate_leases(control):
    task = control.post("/tasks", json={"name": "slices"}).json()["id"]
    control.post(
        "/videos", json={"task_id": task, "path": r"C:\videos\input.avi", "duration_seconds": 65}
    )
    first = control.post("/slices/claim", json={"node_id": "a", "lease_seconds": 10}).json()
    assert first is not None
    assert control.post("/slices/claim", json={"node_id": "a"}).json() is None
    assert control.post("/slices/claim", json={"node_id": "b"}).json()["id"] != first["id"]

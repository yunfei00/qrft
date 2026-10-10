"""报告真实性、安全隔离、取消和真实 Qt 后台生命周期。"""

import json
import threading

import pytest

from qrft.acceptance.report import ITEMS, write_reports
from qrft.acceptance.runner import Cancelled, Runner, decode_console


def test_console_log_utf8_and_windows_ansi_chinese():
    assert decode_console("中文路径".encode()) == "中文路径"
    assert decode_console("中文路径".encode("gbk"), "gbk") == "中文路径"


def test_reports_never_count_blocked_and_escape_html(tmp_path):
    report = {
        "results": [
            {
                "id": k,
                "status": "blocked",
                "reason": "<script>bad</script>",
                "metrics": {"bytes": 10},
            }
            for k in ITEMS
        ]
    }
    write_reports(tmp_path, report)
    saved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert saved["counts"]["passed"] == 0
    assert not saved["candidate_software_gate"]
    assert not saved["hardware_accepted"]
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert (tmp_path / "metrics.csv").read_text(encoding="utf-8-sig").startswith("项目,状态")
    with pytest.raises(FileExistsError):
        write_reports(tmp_path, report)


def test_cancelled_suite_preserves_user_files_and_generates_reports(tmp_path):
    existing = tmp_path / "用户文件.txt"
    existing.write_text("do not change", encoding="utf-8")
    cancel = threading.Event()
    cancel.set()
    runner = Runner(tmp_path, tmp_path, cancel=cancel)
    report = runner.execute()
    assert report["counts"]["skipped"] == len(ITEMS)
    assert existing.read_text(encoding="utf-8") == "do not change"
    assert runner.root != tmp_path and runner.root.parent == tmp_path
    assert (runner.root / "report.html").is_file()
    with pytest.raises(Cancelled):
        runner.check()


def test_hash_benchmark_is_streamed_and_explicitly_not_qr_throughput(tmp_path):
    runner = Runner(tmp_path, tmp_path, selected=["performance"], size_bytes=2 * 1024**2)
    report = runner.execute()
    result = next(r for r in report["results"] if r["id"] == "performance")
    assert result["status"] == "passed"
    assert result["metrics"]["file_bytes"] == 2 * 1024**2
    assert "未测二维码传输" in result["metrics"]["scope"]
    assert len(result["metrics"]["sha256"]) == 64
    assert result["metrics"]["sampled_peak_rss_bytes"] > 0
    assert not report["candidate_software_gate"]


def test_missing_binaries_report_failure_without_claiming_environment_pass(tmp_path):
    runner = Runner(tmp_path, tmp_path, selected=["environment"])
    report = runner.execute()
    assert report["counts"]["failed"] == 1
    assert report["counts"]["passed"] == 0
    assert "缺少完整程序目录" in report["results"][0]["reason"]


def test_failed_integrity_preflight_prevents_executable_start(tmp_path):
    runner = Runner(tmp_path, tmp_path, selected=["environment", "encoder"])
    report = runner.execute()
    assert report["counts"]["failed"] == 1
    assert report["counts"]["blocked"] == 1
    assert not runner.processes


def test_acceptance_qt_worker_cancellation_and_window_close(tmp_path):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from qrft.acceptance.main import AcceptanceWindow

    app = QApplication.instance() or QApplication([])
    window = AcceptanceWindow(tmp_path)
    assert window.smb_share.isHidden()
    window.role.setCurrentIndex(1)
    assert not window.smb_share.isHidden() and window.smb_server.isHidden()
    window.role.setCurrentIndex(0)
    window.output.setText(str(tmp_path))
    for key, checkbox in window.checks.items():
        checkbox.setChecked(key == "performance")
    window.start()
    window.cancel()
    deadline = 100
    while window.job.isRunning() and deadline:
        app.processEvents()
        QTest.qWait(10)
        deadline -= 1
    assert not window.job.isRunning()
    app.processEvents()
    assert window.start_button.isEnabled()
    assert (window.job.runner.root / "report.json").is_file()
    window.close()


def test_headless_selected_performance_does_not_claim_complete_candidate(tmp_path):
    from qrft.acceptance.main import main

    assert (
        main(
            [
                "--headless",
                "--programs",
                str(tmp_path),
                "--output",
                str(tmp_path),
                "--items",
                "performance",
                "--size-mb",
                "1",
            ]
        )
        == 0
    )
    report = json.loads(next(tmp_path.glob("*/report.json")).read_text(encoding="utf-8"))
    assert not report["candidate_software_gate"]
    assert report["counts"]["passed"] == 1


def test_synthetic_zxing_metrics_use_real_qr_video_not_mock(tmp_path):
    from qrft.encoder_cli.main import export_frames

    runner = Runner(tmp_path, tmp_path, selected=["qr_performance"])
    export_frames(runner.source, runner.images, chunk_size=64)
    runner.make_video(runner.images, runner.video)
    report = runner.execute()
    result = next(r for r in report["results"] if r["id"] == "qr_performance")
    assert result["status"] == "passed"
    assert result["metrics"]["decoded_qr_frames"] == 210
    assert result["metrics"]["sampled_video_frames"] == 210
    assert result["metrics"]["unrecognized_sample_fraction"] == 0
    assert not report["hardware_accepted"]


def test_control_acceptance_identity_is_optional_and_contains_no_token(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from qrft.control.app import app

    monkeypatch.delenv("QRFT_ACCEPTANCE_ID", raising=False)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    monkeypatch.setenv("QRFT_ACCEPTANCE_ID", "owned-session")
    monkeypatch.setenv("QRFT_API_TOKEN", "private-token")
    assert client.get("/health").json() == {"status": "ok", "acceptance_instance": "owned-session"}
    assert client.get("/acceptance/nodes").status_code == 401
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "should-not-create.db"))
    assert (
        client.post(
            "/tasks",
            json={"name": "must not mutate"},
            headers={
                "Authorization": "Bearer private-token",
                "X-QRFT-Acceptance-ID": "other-session",
            },
        ).status_code
        == 409
    )
    assert not (tmp_path / "should-not-create.db").exists()


def test_smb_single_host_is_blocked_not_passed(tmp_path):
    report = Runner(tmp_path, tmp_path, selected=["smb"]).execute()
    result = next(r for r in report["results"] if r["id"] == "smb")
    assert result["status"] == "blocked"
    assert "真实双机 SMB：未验收" in result["reason"]


def test_token_redacted_from_persistent_logs(tmp_path):
    runner = Runner(tmp_path, tmp_path, smb_token="private-secret-token")
    runner.log("error private-secret-token")
    assert "private-secret-token" not in (runner.root / "acceptance.log").read_text(
        encoding="utf-8"
    )


def test_role_registry_and_slice_metrics_keep_auth_and_real_batch_counts(tmp_path, monkeypatch):
    import base64

    from fastapi.testclient import TestClient

    from qrft.control.app import app
    from qrft.core.protocol import encode_data

    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "evidence.db"))
    monkeypatch.setenv("QRFT_API_TOKEN", "secret")
    client = TestClient(app)
    assert client.get("/acceptance/nodes").status_code == 401
    assert client.get("/acceptance/slices?video_id=1").status_code == 401
    client.headers.update({"Authorization": "Bearer secret"})
    evidence = {
        "node_id": "A",
        "machine_id": "a" * 64,
        "hostname": "Windows-A",
        "video_path": r"\\server\share\video.avi",
    }
    assert client.post("/acceptance/nodes", json=evidence).status_code == 200
    assert client.get("/acceptance/nodes").json()[0]["video_path"] == evidence["video_path"]
    assert (
        client.post("/acceptance/nodes", json={**evidence, "machine_id": "invalid"}).status_code
        == 422
    )
    task = client.post("/tasks", json={"name": "actual receipts"}).json()["id"]
    video = client.post(
        "/videos", json={"task_id": task, "path": "test.avi", "duration_seconds": 1}
    ).json()["id"]
    lease = client.post("/slices/claim", json={"node_id": "A", "lease_seconds": 120}).json()
    frame = base64.b64encode(encode_data(0, b"binary")).decode()
    body = {
        "task_id": task,
        "slice_id": lease["id"],
        "lease_token": lease["lease_token"],
        "frames_base64": [frame, frame, base64.b64encode(encode_data(0, b"wrong")).decode()],
    }
    assert client.post("/packets/batch", json=body).json() == {
        "inserted": 1,
        "duplicate": 1,
        "conflict": 1,
    }
    client.post(
        f"/slices/{lease['id']}/complete",
        json={"node_id": "A", "lease_token": lease["lease_token"]},
    )
    receipt = client.get(f"/acceptance/slices?video_id={video}").json()[0]
    assert receipt["frames"] == 3 and receipt["inserted"] == 1
    assert receipt["duplicates"] == 1 and receipt["conflicts"] == 1
    assert receipt["completed_at"] >= receipt["started_at"]

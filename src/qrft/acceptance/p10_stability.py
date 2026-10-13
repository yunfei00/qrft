"""Native Qt endurance while repeatedly decoding a bounded medium MP4."""

from __future__ import annotations

import html
import json
import os
import sqlite3
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qrft.acceptance.benchmark import byte_equal
from qrft.acceptance.resources import ProcessSampler, environment, own_process, save_json
from qrft.decoder_gui.acceptance import Actor


def run(root, budget, fixture_path, seconds=600):
    if os.name != "nt":
        raise RuntimeError("P10 native Windows GUI stability requires a Windows desktop")
    if fixture_path is None or not 1 <= seconds <= 3600:
        raise ValueError("fixture and controlled 1..3600-second duration required")
    budget.check(force=True)
    if budget.total_seconds - (time.monotonic() - budget.started) < seconds + 120:
        raise TimeoutError("BLOCKED_BY_LIMIT: insufficient total budget for stability run")
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    directory = root / f"stability-{seconds}s"
    directory.mkdir(exist_ok=False)
    (directory / "screenshots").mkdir()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    actor = Actor(directory, directory / "workspace")
    sampler = ProcessSampler(directory / "resources.jsonl")
    tick_count = [0]
    actor.tick_timer.timeout.disconnect()
    actor.tick_timer.timeout.connect(lambda: tick_count.__setitem__(0, tick_count[0] + 1))
    report = {
        "environment": environment(),
        "scope": "native Windows Qt GUI + repeated short synthetic MP4 scans, NOT a single long video",
        "requested_seconds": seconds,
    }
    try:
        actor.open()
        assert actor.app.platformName() == "windows"
        actor.configure(workers=2, slices=1)
        task = actor.task(f"P10 {seconds}-second bounded endurance")
        actor.drop(Path(fixture["video"]))
        actor.click_idle("开始 / 继续")
        actor.track()
        actor.window.timer.start(1000)
        actor.screenshot("start")
        started = time.monotonic()
        next_poll = started
        cycles, snapshots, reopened = 0, [], False
        recovery = None
        while time.monotonic() - started < seconds:
            actor.app.processEvents()
            rss = sampler.sample([own_process()])
            budget.check(rss=rss)
            now = time.monotonic()
            if now >= next_poll:
                next_poll = now + 1
                progress = actor.progress()
                assert progress["conflicts"] == 0
                if progress["slices"] and all(s["state"] == "done" for s in progress["slices"]):
                    assert progress["stored"] == (fixture["source_bytes"] + 1399) // 1400
                    if recovery is None:
                        actor.idle()
                        actor.window.refresh()
                        actor.idle()
                        recovery = actor.progress()["recovery"]
                        assert recovery["status"] == "verified"
                        assert recovery["md5"] == fixture["hashes"]["md5"]
                        assert recovery["sha256"] == fixture["hashes"]["sha256"]
                        assert byte_equal(Path(fixture["source"]), Path(recovery["path"]))
                    cycles += 1
                    for video in actor.window.session.client.request(f"/videos?task_id={task}"):
                        actor.window.session.client.request(f"/videos/{video['id']}/rescan", {})
                if len(snapshots) == 0 or now - started >= len(snapshots) * 60:
                    snapshot = {
                        "elapsed_seconds": now - started,
                        "cycles": cycles,
                        "stored": progress["stored"],
                        "duplicates": progress["duplicates"],
                        "slices": progress["slices"],
                        "pending_gui_jobs": actor.window.pending_jobs,
                        "online_nodes": sum(
                            n["status"] == "online"
                            for n in actor.window.session.client.request("/nodes")
                        ),
                        "rss_bytes": rss,
                        "database_bytes": (actor.window.session.state / "control.sqlite3")
                        .stat()
                        .st_size,
                        "wal_bytes": (actor.window.session.state / "control.sqlite3-wal")
                        .stat()
                        .st_size
                        if (actor.window.session.state / "control.sqlite3-wal").exists()
                        else 0,
                    }
                    snapshots.append(snapshot)
                    actor.screenshot(f"minute-{len(snapshots):02d}")
                    save_json(directory / "progress.json", snapshots)
                    print(
                        f"stability {seconds}s: elapsed={now - started:.0f}s cycles={cycles} rss={rss}",
                        flush=True,
                    )
                if not reopened and now - started >= seconds / 2:
                    actor.window.timer.stop()
                    actor.idle()
                    stored_before = actor.progress()["stored"]
                    actor.close()
                    actor.open()
                    actor.configure(workers=2, slices=1)
                    assert actor.window.task_id() == task
                    assert actor.progress()["stored"] >= stored_before
                    actor.click_idle("开始 / 继续")
                    actor.track()
                    actor.window.timer.start(1000)
                    reopened = True
            QTest.qWait(100)
        elapsed = time.monotonic() - started
        assert recovery is not None and cycles > 0
        actor.window.timer.stop()
        actor.idle()
        actor.click_idle("停止并保存")
        actor.screenshot("end")
        sampler.sample([own_process()], force=True)
        actor.close()
        with sqlite3.connect(directory / "workspace/.qrft-decoder/control.sqlite3") as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            receipt_totals = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(frames),0),COUNT(DISTINCT node_id) FROM slice_receipts WHERE completed_at IS NOT NULL"
            ).fetchone()
        errors = [e for e in actor.events if e["status"] == "error"]
        # Any background failure is visible in the raw report and fails endurance.
        assert not errors, errors[-3:]
        report.update(
            status="PASS",
            actual_seconds=elapsed,
            native_qt_platform=actor.app.platformName(),
            scans_completed=cycles,
            repeated_video_bytes=fixture["video_bytes"],
            repeated_media={k: v for k, v in fixture["media"].items() if k != "path"},
            completed_slice_receipts=receipt_totals[0],
            submitted_data_and_finish_frames=receipt_totals[1],
            distinct_local_nodes=receipt_totals[2],
            gui_control_reopened_midway=reopened,
            resource_samples=sampler.summary(),
            minute_snapshots=snapshots,
            qt_timer_ticks=tick_count[0],
            background_error_count=len(errors),
            sqlite_integrity_check="ok",
            owned_processes_alive_after_close=0,
            final_hashes=fixture["hashes"],
        )
        save_json(directory / "report.json", report)
        (directory / "report.html").write_text(
            '<!doctype html><meta charset="utf-8"><h1>P10 原生 GUI 稳定性</h1><pre>'
            + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
            + '</pre><a href="screenshots/start.png">开始截图</a> <a href="screenshots/end.png">结束截图</a>',
            encoding="utf-8",
        )
        return report
    finally:
        if actor.window and actor.window.job.isRunning():
            actor.close()
        log = actor.window.log.toPlainText() if actor.window else ""
        for token in set(actor.tokens):
            log = log.replace(token, "[REDACTED]")
        (directory / "gui.log").write_text(log, encoding="utf-8")
        actor.dialog_timer.stop()
        actor.tick_timer.stop()
        sampler.close()

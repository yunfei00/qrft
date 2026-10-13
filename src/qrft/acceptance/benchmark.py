"""Generate once, then fairly scan the same real MP4 with independent Workers."""

from __future__ import annotations

import hashlib
import random
import sqlite3
import statistics
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from pathlib import Path

import cv2
import numpy as np

from qrft.acceptance.resources import ProcessSampler, ResourceLimit, own_process, save_json
from qrft.core.qr_image import v2_image
from qrft.decoder_gui.service import ManagedSession, inspect_video
from qrft.encoder_cli.playback import iter_encoded_frames


def hashes(path: Path) -> dict:
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            md5.update(block)
            sha.update(block)
    return {"md5": md5.hexdigest().upper(), "sha256": sha.hexdigest()}


def byte_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as a, second.open("rb") as b:
        while block := a.read(1024 * 1024):
            if block != b.read(len(block)):
                return False
    return True


def _canvas(raw):
    image = v2_image(raw)
    h, w = image.shape[:2]
    y, x = (926 - h) // 2, (926 - w) // 2
    canvas = np.full((926, 926, 3), 255, dtype=np.uint8)
    canvas[y : y + h, x : x + w] = image
    return canvas


def rendered_frames(source, count, stats):
    """Ordered output and at most 2*N queued frames; repeated controls share results."""
    previous, rendered = None, None
    if count == 1:
        for _, raw in iter_encoded_frames(source, protocol_version=2):
            if raw != previous:
                rendered = _canvas(raw)
                previous = raw
            stats["max_pending_frames"] = 1
            yield rendered
        return
    pending = deque()
    limit = count * 2
    with ProcessPoolExecutor(max_workers=count) as pool:
        for _, raw in iter_encoded_frames(source, protocol_version=2):
            if raw != previous:
                rendered = pool.submit(_canvas, raw)
                previous = raw
            pending.append(rendered)
            stats["max_pending_frames"] = max(stats["max_pending_frames"], len(pending))
            if len(pending) == limit:
                yield pending.popleft().result(timeout=30)
        while pending:
            yield pending.popleft().result(timeout=30)


def generate_fixture(directory: Path, size_kib: int, budget=None, *, render_processes=1) -> dict:
    if size_kib <= 0:
        raise ValueError("size_kib must be positive")
    if size_kib >= 1024 * 1024:
        raise ResourceLimit("P10 forbids generating a full 1 GiB or larger QR video")
    if not 1 <= render_processes <= 4:
        raise ValueError("1..4 bounded rendering processes required")
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    source, video = directory / "benchmark.bin", directory / "synthetic.mp4"
    generator = random.Random(928)
    sampler = ProcessSampler(directory / "encoding-resources.jsonl")
    writer = None
    try:
        with source.open("xb") as stream:
            remaining = size_kib * 1024
            while remaining:
                if budget:
                    budget.check(item_started=started, reserve_bytes=min(remaining, 1024**2))
                block = generator.randbytes(min(remaining, 65536))
                stream.write(block)
                remaining -= len(block)
        expected = hashes(source)
        encoded = time.monotonic()
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
        if not writer.isOpened():
            raise OSError("MP4 codec unavailable")
        stats = {"max_pending_frames": 0}
        with closing(rendered_frames(source, render_processes, stats)) as rendered:
            for frames, canvas in enumerate(rendered, 1):
                writer.write(canvas)
                rss = sampler.sample([own_process()])
                if budget:
                    budget.check(item_started=started, rss=rss)
                if frames % 250 == 0:
                    print(f"encode {size_kib} KiB: {frames} frames", flush=True)
        writer.release()
        writer = None
        encoding_seconds = time.monotonic() - encoded
        info = inspect_video(video)
        assert info["frames"] == (size_kib * 1024 + 1399) // 1400 + 40
        fixture = {
            "source": str(source.resolve()),
            "source_bytes": source.stat().st_size,
            "video": str(video.resolve()),
            "media": info,
            "video_bytes": video.stat().st_size,
            "encoding_seconds": encoding_seconds,
            "hashes": expected,
            "video_sha256": hashes(video)["sha256"],
            "encoding_resources": sampler.summary(),
            "render_processes": render_processes,
            "render_queue_limit_frames": max(1, render_processes * 2),
            "maximum_pending_render_frames": stats["max_pending_frames"],
        }
        save_json(directory / "fixture.json", fixture)
        return fixture
    finally:
        if writer is not None:
            writer.release()
        sampler.close()


def scan_fixture(
    directory: Path,
    fixture: dict,
    workers: int,
    *,
    budget=None,
    slice_seconds=1,
    timeout=1800,
    interrupt_once=False,
) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    session = ManagedSession(directory / "workspace")
    sampler = ProcessSampler(directory / "scan-resources.jsonl")
    task = None
    try:
        task = session.client.request(
            "/tasks", {"name": "same-video benchmark", "protocol_version": 2}
        )["id"]
        video = session.client.request(
            "/videos",
            {
                "task_id": task,
                "path": fixture["video"],
                "duration_seconds": fixture["media"]["duration_seconds"],
                "slice_seconds": slice_seconds,
            },
        )["id"]
        started = time.monotonic()
        session.start(task, workers)
        roots = [session.control, *session.workers]
        worker_pids = [p.pid for p in session.workers]
        interruption = None
        while time.monotonic() - started < timeout:
            rss = sampler.sample(roots)
            if budget:
                budget.check(item_started=started, rss=rss)
            progress = session.client.request(f"/tasks/{task}/progress")
            if interrupt_once and interruption is None and progress["stored"] >= 100:
                session.pause(task)
                paused = session.client.request(f"/tasks/{task}/progress")
                assert paused["paused"] and paused["stored"] >= progress["stored"]
                interruption = {
                    "paused_stored": paused["stored"],
                    "elapsed": time.monotonic() - started,
                }
                session.start(task, workers)
                roots.extend(session.workers)
                continue
            if progress["slices"] and all(s["state"] == "done" for s in progress["slices"]):
                break
            if any(p.poll() is not None for p in session.workers):
                raise RuntimeError("benchmark Worker exited before completion")
            time.sleep(0.1)
        else:
            raise TimeoutError("BLOCKED_BY_LIMIT: benchmark scan timed out")
        scan_seconds = time.monotonic() - started
        receipts = session.client.request(f"/acceptance/slices?video_id={video}")
        completed = [r for r in receipts if r["completed_at"] is not None]
        nodes = sorted({r["node_id"] for r in completed})
        assert len(nodes) >= workers if interrupt_once else len(nodes) == workers, (
            f"only {len(nodes)} Workers actually processed slices"
        )
        recovery_started = time.monotonic()
        result = session.client.request(f"/tasks/{task}/recover", {})
        recovery_seconds = time.monotonic() - recovery_started
        assert result["status"] == "verified"
        assert result["md5"] == fixture["hashes"]["md5"]
        assert result["sha256"] == fixture["hashes"]["sha256"]
        equal = byte_equal(Path(fixture["source"]), Path(result["path"]))
        assert equal and progress["missing_count"] == 0 and progress["conflicts"] == 0
        sampler.sample(roots, force=True)
        with sqlite3.connect(session.state / "control.sqlite3") as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            assert integrity == "ok"
        report = {
            "status": "PASS",
            "scope": "same synthetic MP4 / OpenCV-ZXing / independent Worker HTTP / SQLite / real recovery",
            "workers": workers,
            "worker_root_pids": worker_pids,
            "pause_resume_interruption": interruption,
            "nodes_with_completed_slices": nodes,
            "slice_seconds": slice_seconds,
            "slice_overlap_ms": min(1000, slice_seconds * 100),
            "source_bytes": fixture["source_bytes"],
            "video_sha256": fixture["video_sha256"],
            "scan_seconds": scan_seconds,
            "recovery_seconds": recovery_seconds,
            "verified_unique_packets": progress["stored"],
            "effective_packets_per_second": progress["stored"] / scan_seconds,
            "synthetic_scan_payload_bytes_per_second": fixture["source_bytes"] / scan_seconds,
            "missing_count": progress["missing_count"],
            "conflicts": progress["conflicts"],
            "duplicates": progress["duplicates"],
            "hashes": fixture["hashes"],
            "bytes_equal": equal,
            "resources": sampler.summary(),
            "database_bytes": (session.state / "control.sqlite3").stat().st_size,
            "sqlite_integrity_check": integrity,
            "receipts": completed,
            "workspace": "workspace/",
            "log_directory": "workspace/.qrft-decoder/logs/",
        }
        session.close()
        # A new independent Control process must see the same persistent result.
        session = ManagedSession(directory / "workspace")
        reopened = session.client.request(f"/tasks/{task}/progress")
        assert reopened["stored"] == progress["stored"]
        assert reopened["recovery"]["status"] == "verified"
        report["reopened_persistent_result"] = True
        save_json(directory / "report.json", report)
        return report
    finally:
        session.close()
        sampler.close()


def summarize(runs):
    groups = []
    for count in sorted({r["workers"] for r in runs}):
        values = [r for r in runs if r["workers"] == count]
        times = [r["scan_seconds"] for r in values]
        groups.append(
            {
                "workers": count,
                "repeats": len(values),
                "scan_median_seconds": statistics.median(times),
                "scan_min_seconds": min(times),
                "scan_max_seconds": max(times),
                "packets_per_second_median": statistics.median(
                    r["effective_packets_per_second"] for r in values
                ),
                "rss_peak_max_bytes": max(r["resources"]["rss_peak_bytes"] for r in values),
                "cpu_peak_max_percent": max(r["resources"]["cpu_peak_percent"] for r in values),
                "process_io_read_median_bytes": statistics.median(
                    r["resources"]["process_io_read_bytes"] for r in values
                ),
                "process_io_write_median_bytes": statistics.median(
                    r["resources"]["process_io_write_bytes"] for r in values
                ),
            }
        )
    single = next((g["scan_median_seconds"] for g in groups if g["workers"] == 1), None)
    for group in groups:
        group["speedup_vs_one_worker"] = single / group["scan_median_seconds"] if single else None
    return groups

"""Reproducible synthetic MP4 + real network Worker benchmark, not screen transfer."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import subprocess
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
import psutil

from qrft.core.qr_image import v2_image
from qrft.decoder_gui.service import ManagedSession, inspect_video
from qrft.encoder_cli.playback import iter_encoded_frames


def run(directory: Path, size_kib: int, workers: int) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    source = directory / "benchmark.bin"
    generator = random.Random(928)
    expected = hashlib.md5(usedforsecurity=False)
    with source.open("xb") as stream:
        remaining = size_kib * 1024
        while remaining:
            block = generator.randbytes(min(remaining, 65536))
            stream.write(block)
            expected.update(block)
            remaining -= len(block)
    video = directory / "synthetic.mp4"
    encode_started = time.monotonic()
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
    if not writer.isOpened():
        raise OSError("MP4 codec unavailable")
    previous, canvas = None, None
    try:
        for _, raw in iter_encoded_frames(source, protocol_version=2):
            if raw != previous:
                image = v2_image(raw)
                h, w = image.shape[:2]
                y, x = (926 - h) // 2, (926 - w) // 2
                canvas = np.full((926, 926, 3), 255, dtype=np.uint8)
                canvas[y : y + h, x : x + w] = image
                previous = raw
            writer.write(canvas)
    finally:
        writer.release()
    encoding_seconds = time.monotonic() - encode_started
    session = ManagedSession(directory / "workspace")
    try:
        task = session.client.request(
            "/tasks", {"name": "synthetic benchmark", "protocol_version": 2}
        )["id"]
        info = inspect_video(video)
        session.client.request(
            "/videos",
            {
                "task_id": task,
                "path": info["path"],
                "duration_seconds": info["duration_seconds"],
                "slice_seconds": 1,
            },
        )
        started = time.monotonic()
        session.start(task, workers)
        roots = [psutil.Process(p.pid) for p in [session.control, *session.workers]]
        processes = {}
        rss_peak, cpu_peak, read_bytes, write_bytes = 0, 0, 0, 0
        while time.monotonic() - started < max(120, size_kib * 5):
            rss = cpu = reads = writes = 0
            for root in roots:
                for process in [root, *root.children(recursive=True)]:
                    if process.pid not in processes:
                        processes[process.pid] = process
                        process.cpu_percent()
            for process in processes.values():
                if not process.is_running():
                    continue
                rss += process.memory_info().rss
                cpu += process.cpu_percent()
                io = process.io_counters()
                reads += io.read_bytes
                writes += io.write_bytes
            rss_peak, cpu_peak = max(rss_peak, rss), max(cpu_peak, cpu)
            read_bytes, write_bytes = max(read_bytes, reads), max(write_bytes, writes)
            progress = session.client.request(f"/tasks/{task}/progress")
            if progress["slices"] and all(row["state"] == "done" for row in progress["slices"]):
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("benchmark scan timed out")
        scan_seconds = time.monotonic() - started
        recover_started = time.monotonic()
        result = session.client.request(f"/tasks/{task}/recover", {})
        recovery_seconds = time.monotonic() - recover_started
        assert result["status"] == "verified" and result["md5"] == expected.hexdigest().upper()
        report = {
            "scope": "自动合成 MP4 + 真实 OpenCV/ZXing + 独立 Worker HTTP/SQLite；不是屏幕录制或文件哈希测速",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor(),
            "logical_cpus": psutil.cpu_count(),
            "memory_total_bytes": psutil.virtual_memory().total,
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
            ).stdout.strip(),
            "source_state": "工作树源码，报告应同时保存源码提交/修改状态",
            "git_worktree_dirty": bool(
                subprocess.run(
                    ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
                ).stdout
            ),
            "measured_processes": len(processes),
            "workers": workers,
            "source_bytes": size_kib * 1024,
            "media": info,
            "encoding_seconds": encoding_seconds,
            "scan_seconds": scan_seconds,
            "recovery_seconds": recovery_seconds,
            "verified_unique_packets": progress["stored"],
            "effective_packets_per_second": progress["stored"] / scan_seconds,
            "synthetic_scan_payload_bytes_per_second": size_kib * 1024 / scan_seconds,
            "missing_count": progress["missing_count"],
            "duplicates": progress["duplicates"],
            "aggregate_process_rss_peak_bytes": rss_peak,
            "aggregate_cpu_peak_percent": cpu_peak,
            "process_io_read_bytes": read_bytes,
            "process_io_write_bytes": write_bytes,
            "resource_sampling_seconds": 0.1,
            "md5": result["md5"],
            "sha256": result["sha256"],
            "not_verified": ["真实录屏吞吐率", "长视频", "1GB 二维码全链路", "真实双 Windows/SMB"],
        }
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="合成 MP4 解码性能测量；不代表真实录屏")
    parser.add_argument("--size-kib", type=int, default=16)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=2)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.size_kib <= 0:
        parser.error("size-kib must be positive")
    directory = args.directory or Path("temp") / f"decoder-benchmark-{uuid.uuid4().hex}"
    print(json.dumps(run(directory, args.size_kib, args.workers), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

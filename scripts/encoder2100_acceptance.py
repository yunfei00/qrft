"""Reproducible independent encoder evidence, not an application decoder or GUI."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import platform
import shutil
import statistics
import sys
import threading
import time
from pathlib import Path

import psutil

from qrft.encoder2100.encoder import Source, export, select
from qrft.encoder2100.protocol import CHUNK_SIZE, data_frame
from qrft.encoder2100.qr import image, png


class Monitor:
    def __init__(self, include_children=False):
        self.include_children = include_children

    def __enter__(self):
        self.done = threading.Event()
        self.samples = []
        process = psutil.Process()
        known = {process.pid: process}

        def collect():
            while not self.done.is_set():
                try:
                    if self.include_children:
                        for child in process.children(recursive=True):
                            known.setdefault(child.pid, child)
                    rss, cpu = 0, 0
                    for child in list(known.values()):
                        try:
                            rss += child.memory_info().rss
                            cpu += child.cpu_percent()
                        except psutil.Error:
                            known.pop(child.pid, None)
                    self.samples.append(
                        {
                            "time": time.perf_counter(),
                            "rss": rss,
                            "cpu": cpu,
                        }
                    )
                except psutil.Error:
                    pass
                self.done.wait(0.025)

        self.thread = threading.Thread(target=collect, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        self.thread.join()

    def summary(self):
        return {
            "rss_peak_bytes": max(x["rss"] for x in self.samples),
            "cpu_peak_percent": max(x["cpu"] for x in self.samples),
            "cpu_average_percent": statistics.mean(x["cpu"] for x in self.samples[1:])
            if len(self.samples) > 1
            else 0,
            "sample_count": len(self.samples),
        }


def read_png(picture):
    import zxingcpp

    result = zxingcpp.read_barcode(picture)
    if result is None:
        raise AssertionError("independent ZXing read failed")
    text = result.text
    assert set(text) <= set("0123456789ABCDEF")
    data = bytes.fromhex(text[:-48])
    assert hashlib.md5(data).hexdigest().upper() == text[-48:-16]
    return int(bytes.fromhex(text[-16:])), data


def large_source(root):
    path = root / "one-gib-sparse.bin"
    with path.open("xb") as stream:
        stream.truncate(1024**3)
    with Monitor() as monitor:
        started = time.perf_counter()
        source = Source(path)
        hashed = time.perf_counter() - started
        amount = 0
        for packet_id, text in source.frames(
            select(source.metadata.packets), repeat_controls=False
        ):
            if packet_id < 88888888:
                amount += len(bytes.fromhex(text[:-48]))
        assert amount == 1024**3
    return {
        "bytes": amount,
        "hash_seconds": hashed,
        "whole_stream_seconds": time.perf_counter() - started,
        **monitor.summary(),
    }


def permission_case(root, source):
    """Real Windows write denial, on a newly created test-only directory."""
    import csv
    import subprocess

    from qrft.encoder_cli.console_test import run_encoder

    denied = root / "permission-denied"
    denied.mkdir(exist_ok=False)
    row = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
    sid = next(csv.reader([row.strip()]))[-1]
    assert sid.startswith("S-1-")
    result = subprocess.run(
        ["icacls", str(denied), "/deny", f"*{sid}:(OI)(CI)(W)"], capture_output=True, check=True
    )
    try:
        result = run_encoder(
            [
                sys.executable,
                "-m",
                "qrft.encoder2100.cli",
                "export",
                str(source),
                "--output",
                str(denied / "output"),
            ],
            timeout=30,
        )
        assert result.returncode == 2 and not (denied / "output").exists(), result.stdout
        return {"status": "PASS", "actual_os_denial": True, "exit_code": result.returncode}
    finally:
        subprocess.run(
            ["icacls", str(denied), "/remove:d", f"*{sid}"], capture_output=True, check=True
        )


def benchmark(root):
    import cv2
    import numpy as np
    from PIL import Image

    root.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root.parent).free < 3 * 1024**3:
        raise OSError("验收需至少 3 GiB 空闲空间")
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "protocol": "QRFT2100",
        "python": platform.python_version(),
        "os": platform.platform(),
        "status": "RUNNING",
    }
    try:
        payload = os.urandom(100 * CHUNK_SIZE)
        source_path = root / "中文,MiX.bin"
        source_path.write_bytes(payload)
        generated = root / "benchmark-png"
        generated.mkdir()
        timings, sizes, recognized = [], [], 0
        with Monitor() as monitor:
            for number in range(100):
                content = payload[number * CHUNK_SIZE : (number + 1) * CHUNK_SIZE]
                started = time.perf_counter()
                raw = png(data_frame(content, number))
                timings.append(time.perf_counter() - started)
                target = generated / f"{number:08d}.png"
                with target.open("xb") as stream:
                    stream.write(raw)
                sizes.append(len(raw))
                assert read_png(Image.open(target)) == (number, content)
                recognized += 1
        report["png"] = {
            "count": 100,
            "full_payload_bytes": CHUNK_SIZE,
            "wire_characters": 4248,
            "version": 40,
            "mode": "ALPHANUMERIC",
            "pixels": [925, 925],
            "generation_seconds_first": timings[0],
            "generation_seconds_total": sum(timings),
            "generation_seconds_median": statistics.median(timings),
            "png_bytes_min": min(sizes),
            "png_bytes_max": max(sizes),
            "zxing_success": recognized,
            "zxing_attempts": 100,
            **monitor.summary(),
        }
        # Actual MP4: first 4 full blocks + short tail, standard 20+5+20 sequence.
        video_source = root / "video-original.bin"
        original = payload[: CHUNK_SIZE * 4 + 11]
        video_source.write_bytes(original)
        source = Source(video_source)
        video = root / "synthetic.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
        if not writer.isOpened():
            raise RuntimeError("MP4 encoder unavailable")
        previous, pixels = None, None
        sequence = []
        try:
            for packet_id, text in source.frames(select(source.metadata.packets)):
                if text != previous:
                    qr = np.asarray(image(text))[:, :, ::-1]
                    pixels = np.full((926, 926, 3), 255, np.uint8)
                    pixels[:925, :925] = qr  # Pad, never resize/crop the original 925 raster.
                    previous = text
                writer.write(pixels)
                sequence.append(packet_id)
        finally:
            writer.release()
        capture = cv2.VideoCapture(str(video))
        actual, blocks = [], {}
        try:
            while True:
                ok, pixels = capture.read()
                if not ok:
                    break
                packet_id, content = read_png(pixels)
                actual.append(packet_id)
                if packet_id < 88888888:
                    blocks[packet_id] = content
        finally:
            capture.release()
        assert actual == sequence
        recovered = b"".join(blocks[i] for i in range(source.metadata.packets))
        assert recovered == original
        report["synthetic_mp4"] = {
            "frames": len(actual),
            "fps": 20,
            "decoded_frames": len(actual),
            "md5": hashlib.md5(recovered).hexdigest().upper(),
            "byte_exact": True,
            "screen_recording": False,
            "bytes": video.stat().st_size,
        }
        missing = root / "missing.txt"
        missing.write_text("1\n00000003\n", encoding="utf-8")
        retransmit = export(
            source, root / "retransmit", select(source.metadata.packets, missing=missing)
        )
        for i in (1, 3):
            assert (
                read_png(Image.open(root / "retransmit" / f"{i:08d}.png"))[1]
                == original[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
            )
        report["selective_retransmission"] = retransmit
        report["permission_denial"] = permission_case(root, video_source)
        # Fresh process prevents QR/MP4 native libraries inflating source-only RSS measurements.
        import subprocess

        process = subprocess.run(
            [sys.executable, __file__, "memory", "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert process.returncode == 0, process.stderr
        report["one_gib_stream_only"] = json.loads(process.stdout)
        report["status"] = "PASS"
    except BaseException as exc:
        report["status"] = "FAIL"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["benchmark", "memory", "native", "timing"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--missing", type=Path)
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()
    if args.mode == "benchmark":
        benchmark(args.root)
    elif args.mode == "memory":
        print(json.dumps(large_source(args.root)))
    elif args.mode == "native":
        from qrft.encoder_cli.console_test import run_encoder

        command = [
            sys.executable,
            "-m",
            "qrft.encoder2100.cli",
            "play",
            str(args.root / "中文,MiX.bin"),
            "--log",
            str(args.root / "native-player.jsonl"),
        ]
        if args.missing:
            command.extend(["--missing", str(args.missing)])
        if args.fullscreen:
            command.append("--fullscreen")
        with Monitor(include_children=True) as monitor:
            result = run_encoder(command, timeout=300)
        (args.root / "native-resources.json").write_text(json.dumps(monitor.summary(), indent=2))
        (args.root / "native-console.log").write_text(result.stdout, encoding="utf-8")
        raise SystemExit(result.returncode)
    else:
        events = [
            json.loads(line)
            for line in (args.root / "native-player.jsonl").read_text().splitlines()
        ]
        display = [x for x in events if x["event"] == "display"]
        source = Source(args.root / "中文,MiX.bin")
        selected = select(source.metadata.packets, missing=args.missing)
        expected_ids = [number for number, _ in source.frames(selected)]
        assert [e["packet_id"] for e in display] == expected_ids
        assert events[0]["state"] == "READY"
        started = next(e["time"] for e in events if e["event"] == "state")
        assert sum(e["time"] < started for e in display) == 1
        changes = [e for e in events if e["event"] == "state"]
        for before, after in itertools.pairwise(changes):
            if before["state"] == "PAUSED":
                assert before["position"] == after["position"]
        gaps = [b["time"] - a["time"] for a, b in itertools.pairwise(display[1:])]
        active_gaps = [
            b["time"] - a["time"]
            for a, b in itertools.pairwise(display[1:])
            if not any(
                e["event"] == "state"
                and e.get("state") == "PAUSED"
                and a["time"] <= e["time"] <= b["time"]
                for e in events
            )
        ]
        report = {
            "displayed_frames": len(display),
            "completed": any(x["event"] == "completed" for x in events),
            "state_changes": [x for x in events if x["event"] == "state"],
            "interval_seconds_min": min(gaps),
            "interval_seconds_median": statistics.median(gaps),
            "interval_seconds_max": max(gaps),
            "buffering_events": sum(x["event"] == "buffering" for x in events),
            "active_interval_seconds_min": min(active_gaps),
            "active_interval_seconds_median": statistics.median(active_gaps),
            "active_interval_seconds_p95": sorted(active_gaps)[int((len(active_gaps) - 1) * 0.95)],
            "active_interval_seconds_max": max(active_gaps),
            "active_interval_jitter_stdev_seconds": statistics.pstdev(active_gaps),
            "note": "includes measured pause if present; synthetic content/native OpenCV, not screen recorder throughput",
        }
        (args.root / "player-timing.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))


if __name__ == "__main__":
    main()

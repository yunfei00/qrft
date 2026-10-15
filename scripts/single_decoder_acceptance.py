"""Reproducible synthetic MP4 loss/retransmission/folder recovery, not screen capture."""

import argparse
import hashlib
import json
import random
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import cv2
import numpy as np

from qrft.encoder2100.encoder import Source, select
from qrft.encoder2100.qr import image
from qrft.single_decoder.project import decode_project


def write_video(path, sequence):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
    if not writer.isOpened():
        raise OSError("MP4 encoder unavailable")
    try:
        for text in sequence:
            pixels = np.full((926, 926, 3), 255, np.uint8)
            pixels[:925, :925] = np.asarray(image(text))[:, :, ::-1]
            writer.write(pixels)
    finally:
        writer.release()


def run(root):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    report = {"status": "RUNNING", "synthetic_video": True, "physical_screen_recording": False}
    try:
        source_folder = root / "Folder 中文"
        (source_folder / "Empty Space").mkdir(parents=True)
        (source_folder / ".hidden").write_bytes(b"\x00\xff")
        (source_folder / "zero.bin").write_bytes(b"")
        (source_folder / "random, MiX.bin").write_bytes(random.Random(345).randbytes(5200))
        with Source(source_folder) as source:
            details = source.describe()
            sequence = list(source.frames(select(source.metadata.packets)))
            with source.open_stream() as stream:
                expected_zip = stream.read()
        project = root / "project"
        (project / "videos").mkdir(parents=True)
        assert details["packets"] >= 2
        first = [text for number, text in sequence if number != 1]
        write_video(project / "videos/01-main.mp4", first + [first[1]])
        partial = decode_project(project)
        assert partial["status"] == "INCOMPLETE" and partial["missing_packets"] == 1
        missing = project / "reports/missing_packets.txt"
        ranges = select(details["packets"], missing=missing)
        assert ranges == [(1, 1)]
        with Source(source_folder, expected_archive_md5=details["archive_zip_md5"]) as retry:
            retry_frames = [text for _, text in retry.frames(ranges)]
        write_video(project / "videos/02-retry.mp4", retry_frames)
        complete = decode_project(project)
        assert complete["status"] == "SUCCESS" and complete["videos_skipped"] == 1
        restored = project / complete["output_path"]
        assert restored.read_bytes() == expected_zip
        assert complete["actual_md5"] == details["archive_zip_md5"]
        assert complete["folder"]["folder_content_md5"] == details["folder_content_md5"]
        assert complete["folder"]["folder_content_sha256"] == details["folder_content_sha256"]
        repeated = decode_project(project)
        assert repeated["status"] == "SUCCESS" and repeated["videos_skipped"] == 2
        command = subprocess.run(
            [sys.executable, "-m", "qrft", "decode", str(project)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert command.returncode == 0 and "MD5: PASS" in command.stdout
        with closing(sqlite3.connect(project / "state/project.db")) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            blob_count = connection.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
            receipt_count = connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            assert blob_count == details["packets"] + 2
            assert receipt_count == details["packets"] + 4
            videos = [
                dict(zip(("path", "status", "frames", "attempts"), row))
                for row in connection.execute(
                    "SELECT path,status,processed_frames,attempts FROM videos ORDER BY path"
                )
            ]
        report.update(
            status="PASS",
            protocol="QRFT2100",
            source=details,
            partial=partial,
            complete=complete,
            repeated=repeated,
            videos=videos,
            cli_stdout=command.stdout,
            cli_exit=command.returncode,
            zip_byte_exact=True,
            unique_packet_blobs=blob_count,
            source_receipts=receipt_count,
            restored_sha256=hashlib.sha256(expected_zip).hexdigest().upper(),
            seconds=time.perf_counter() - started,
        )
    except BaseException as exc:
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        (root / "acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    run(parser.parse_args().root)

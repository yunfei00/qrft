"""Reproducible RAM ZIP/ZXing/MP4 acceptance, with no archive files on disk."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from encoder2100_acceptance import Monitor, read_png

from qrft.encoder2100.encoder import Source, select
from qrft.encoder2100.protocol import FINISH_ID, START_ID
from qrft.encoder2100.qr import png


def run(root):
    import cv2
    import numpy as np
    from PIL import Image

    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "RUNNING", "screen_recording": False}
    try:
        folder = root / "Input 中文"
        folder.mkdir()
        (folder / "Empty 目录").mkdir()
        (folder / "Nested").mkdir()
        (folder / "Nested" / "Zero.bin").write_bytes(b"")
        (folder / "Nested" / "MiX,#&[].EXE").write_bytes(random.Random(2100).randbytes(5003))
        (folder / ".hidden").write_bytes(bytes(range(256)) * 2)
        originals = {
            p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*")
            if p.is_file()
        }
        footprint = set(root.rglob("*"))
        with Monitor() as monitor:
            begin = time.perf_counter()
            with Source(folder) as source:
                details = source.describe()
                with source.open_stream() as stream:
                    first = stream.read()
                encoded = list(source.frames(select(source.metadata.packets)))
            seconds = time.perf_counter() - begin
        with Source(folder, expected_archive_md5=details["archive_zip_md5"]) as again:
            with again.open_stream() as stream:
                second = stream.read()
            retransmit = list(again.frames([(1, 1)]))
        assert first == second
        assert retransmit[1] == encoded[2]
        assert set(root.rglob("*")) == footprint
        decoded = {}
        pixels = []
        for packet_id, text in encoded:
            raw = png(text)
            picture = Image.open(io.BytesIO(raw))
            assert read_png(picture)[0] == packet_id
            content = read_png(picture)[1]
            decoded[packet_id] = content
            pixels.append(np.asarray(picture)[:, :, ::-1])
        count = details["packets"]
        assert [number for number, _ in encoded] == [START_ID, *range(count), FINISH_ID]
        recovered = b"".join(decoded[i] for i in range(count))
        assert recovered == first
        assert hashlib.md5(recovered).hexdigest().upper() == details["archive_zip_md5"]
        assert decoded[START_ID].decode().rsplit(",", 3)[1] == details["archive_zip_md5"]
        with zipfile.ZipFile(io.BytesIO(recovered)) as zipped:
            assert {
                i.filename: zipped.read(i) for i in zipped.infolist() if not i.is_dir()
            } == originals
            assert json.loads(zipped.comment)["folder_content_md5"] == details["folder_content_md5"]
        video = root / "folder-synthetic.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
        assert writer.isOpened()
        try:
            for picture in pixels:
                padded = np.full((926, 926, 3), 255, np.uint8)
                padded[:925, :925] = picture
                writer.write(padded)
        finally:
            writer.release()
        capture = cv2.VideoCapture(str(video))
        video_frames = []
        try:
            while True:
                ok, picture = capture.read()
                if not ok:
                    break
                video_frames.append(read_png(picture))
        finally:
            capture.release()
        assert video_frames == [(i, decoded[i]) for i, _ in encoded]
        assert b"".join(content for i, content in video_frames if i < START_ID) == first
        report.update(
            folder=details,
            packaging_seconds=seconds,
            rss=monitor.summary(),
            repeated_zip_byte_exact=True,
            png_recognized=len(encoded),
            mp4_recognized=len(video_frames),
            control_counts={"START": 1, "FINISH": 1},
            memory_unzip_verified=True,
            retransmission_byte_exact=True,
            temporary_archive_files=0,
        )
        large = root / "Streaming"
        large.mkdir()
        rng = random.Random(4500)
        with (large / "Random.bin").open("xb") as stream:
            for _ in range(128):
                stream.write(rng.randbytes(64 * 1024))
        with (large / "Zeros.bin").open("xb") as stream:
            for _ in range(512):
                stream.write(bytes(64 * 1024))
        measured = subprocess.run(
            [sys.executable, __file__, "--root", str(root), "--measure-source", str(large)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        report["streaming_40_mib"] = json.loads(measured.stdout)
        try:
            Source(large, max_archive_mib=4)
        except ValueError as exc:
            assert "memory limit" in str(exc)
            report["memory_limit_rejection"] = "PASS"
        else:
            raise AssertionError("RAM bound failed to reject incompressible archive")
        assert not list(root.rglob("*.zip"))
        report["status"] = "PASS"
    except BaseException as exc:
        report.update(status="FAIL", reason=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--measure-source", type=Path)
    args = parser.parse_args()
    if args.measure_source:
        with Monitor() as monitor:
            begin = time.perf_counter()
            with Source(args.measure_source) as source:
                details = source.describe()
            details["seconds"] = time.perf_counter() - begin
        details["rss"] = monitor.summary()
        print(json.dumps(details))
    else:
        run(args.root)


if __name__ == "__main__":
    main()

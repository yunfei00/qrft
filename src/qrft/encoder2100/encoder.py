"""Streaming source inspection, bounded selection and exclusive PNG export."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from .protocol import CHUNK_SIZE, FINISH_ID, START_ID, Metadata, data_frame, frame


def check_cancel(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError("操作已取消；保留本次已生成文件及日志")


class Source:
    def __init__(self, path: Path, cancelled=None):
        self.path = Path(path)
        self.cancelled = cancelled
        before = self.path.stat()
        if not self.path.is_file():
            raise ValueError("输入必须为普通文件")
        self.signature = (before.st_size, before.st_mtime_ns, before.st_ino)
        digest = hashlib.md5()
        with self.path.open("rb") as stream:
            while True:
                check_cancel(cancelled)
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        self.check()
        packets = (before.st_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        if packets > START_ID:
            raise ValueError("文件超出 DATA 编号上限")
        self.metadata = Metadata(
            self.path.name, before.st_size, digest.hexdigest().upper(), packets
        )

    def check(self):
        state = self.path.stat()
        if (state.st_size, state.st_mtime_ns, state.st_ino) != self.signature:
            raise ValueError("源文件在编码期间改变；请保留原文件重新编码")

    def frames(self, ranges, *, repeat_controls=True):
        check_cancel(self.cancelled)
        self.check()
        for _ in range(20 if repeat_controls else 1):
            check_cancel(self.cancelled)
            yield START_ID, self.metadata.start()
        with self.path.open("rb") as stream:
            for first, last in ranges:
                stream.seek(first * CHUNK_SIZE)
                for packet_id in range(first, last + 1):
                    check_cancel(self.cancelled)
                    self.check()
                    expected = min(CHUNK_SIZE, self.metadata.size - packet_id * CHUNK_SIZE)
                    data = stream.read(expected)
                    if len(data) != expected:
                        raise ValueError("源文件读取不完整")
                    yield packet_id, data_frame(data, packet_id)
        self.check()
        for _ in range(20 if repeat_controls else 1):
            check_cancel(self.cancelled)
            yield FINISH_ID, frame(b"finish", FINISH_ID)


def select(packets: int, start=0, end=None, missing: Path | None = None):
    """Store compact ranges, never materialize all packet IDs."""
    if start < 0 or (end is not None and (end < start or end >= packets)):
        raise ValueError("DATA 范围越界")
    if (packets and start >= packets) or (not packets and start):
        raise ValueError("DATA 起始编号越界")
    last = packets - 1 if end is None else end
    if missing is None:
        return [(start, last)] if packets else []
    import re

    ranges = []
    with Path(missing).open(encoding="utf-8-sig") as stream:
        for line in stream:
            text = line.split("#", 1)[0].strip()
            if not text:
                continue
            if not re.fullmatch(r"[0-9]{1,8}(?:-[0-9]{1,8})?", text):
                raise ValueError("缺包清单格式错误")
            parts = text.split("-")
            a, b = int(parts[0]), int(parts[-1])
            if a > b or b >= packets:
                raise ValueError("缺包清单编号越界")
            a, b = max(start, a), min(last, b)
            if a <= b:
                ranges.append((a, b))
            if len(ranges) > 100000:
                raise ValueError("缺包区间超过 100000；请先合并相邻区间")
    merged = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def export(source: Source, output: Path, ranges):
    from .qr import png

    # Preflight before creating any export resources, including START overflow.
    start_png = png(source.metadata.start())
    finish_png = png(frame(b"finish", FINISH_ID))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    written = 0
    with (output / "operations.jsonl").open("x", encoding="utf-8", buffering=1) as log:

        def record(**event):
            log.write(json.dumps(event, ensure_ascii=False) + "\n")

        record(state="started", protocol="QRFT2100", metadata=asdict(source.metadata))
        try:
            for packet_id, text in source.frames(ranges, repeat_controls=False):
                check_cancel(source.cancelled)
                image = (
                    start_png
                    if packet_id == START_ID
                    else finish_png
                    if packet_id == FINISH_ID
                    else png(text)
                )
                if shutil.disk_usage(output).free < len(image) + 1024 * 1024:
                    raise OSError("磁盘空间不足（需保留至少 1 MiB）")
                name = f"{packet_id:08d}.png"
                with (output / name).open("xb") as stream:
                    stream.write(image)
                written += 1
                record(state="written", packet_id=packet_id, png=name)
            check_cancel(source.cancelled)
            source.check()
            result = {
                "protocol": "QRFT2100",
                **asdict(source.metadata),
                "chunk_size": CHUNK_SIZE,
                "ranges": ranges,
                "selected_packets": sum(b - a + 1 for a, b in ranges),
                "png_count": written,
                "control_repeats": 20,
                "complete": True,
            }
            with (output / "manifest.json").open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            record(state="completed", png_count=written)
            return result
        except BaseException as exc:
            record(state="incomplete", error=type(exc).__name__, png_count=written)
            raise

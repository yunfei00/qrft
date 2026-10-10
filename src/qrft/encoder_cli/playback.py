"""实时二维码播放帧生成器：惰性读取文件，不预生成整批图片。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from qrft.core.manifest import inspect_file, selected_ranges
from qrft.core.protocol import encode_data, encode_finish, encode_start


def iter_encoded_frames(
    source: Path,
    *,
    chunk_size: int = 256,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    cancelled=None,
) -> Iterator[tuple[str, bytes]]:
    """START、选定 DATA、FINISH；每次迭代仅读取一个数据包。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    manifest = inspect_file(source, chunk_size, cancelled=cancelled)
    total = int(manifest["total_packets"])
    if start_id < 0 or start_id > total:
        raise ValueError("start_id outside packet range")
    last = total - 1 if end_id is None else end_id
    if last < -1 or last >= total or (last < start_id and not (total == 0 and last == -1)):
        raise ValueError("end_id outside packet range")
    ranges = selected_ranges(total, start_id=start_id, end_id=last, retransmit=retransmit)
    yield "START", encode_start(manifest)
    with source.open("rb") as stream:
        for first, end in ranges:
            stream.seek(first * chunk_size)
            for packet_id in range(first, end + 1):
                if cancelled is not None and cancelled():
                    return
                payload = stream.read(chunk_size)
                if not payload:
                    raise ValueError("source changed during encoding")
                yield f"{packet_id:08d}", encode_data(packet_id, payload)
    yield "FINISH", encode_finish()

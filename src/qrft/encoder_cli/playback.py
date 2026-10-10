"""实时二维码播放帧生成器：惰性读取文件，不预生成整批图片。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from qrft.core.manifest import inspect_file, packet_bytes, parse_packet_list
from qrft.core.protocol import encode_data, encode_finish, encode_start


def iter_encoded_frames(
    source: Path,
    *,
    chunk_size: int = 256,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
) -> Iterator[tuple[str, bytes]]:
    """START、选定 DATA、FINISH；每次迭代仅读取一个数据包。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    manifest = inspect_file(source, chunk_size)
    total = int(manifest["total_packets"])
    if start_id < 0 or start_id > total:
        raise ValueError("start_id outside packet range")
    last = total - 1 if end_id is None else end_id
    if last < -1 or last >= total or (last < start_id and not (total == 0 and last == -1)):
        raise ValueError("end_id outside packet range")
    ids = (
        range(start_id, last + 1)
        if retransmit is None
        else [
            packet_id
            for packet_id in parse_packet_list(retransmit.read_text(encoding="utf-8-sig"), total)
            if start_id <= packet_id <= last
        ]
    )
    yield "START", encode_start(manifest)
    for packet_id in ids:
        yield (
            f"{packet_id:08d}",
            encode_data(packet_id, packet_bytes(source, chunk_size, packet_id)),
        )
    yield "FINISH", encode_finish()

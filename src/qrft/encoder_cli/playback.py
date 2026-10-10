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
) -> Iterator[tuple[str, bytes]]:
    """START、选定 DATA、FINISH；每次迭代仅读取一个数据包。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    manifest = inspect_file(source, chunk_size)
    total = int(manifest["total_packets"])
    ids = (
        range(total)
        if retransmit is None
        else parse_packet_list(retransmit.read_text(encoding="utf-8-sig"), total)
    )
    yield "START", encode_start(manifest)
    for packet_id in ids:
        yield f"{packet_id:08d}", encode_data(
            packet_id, packet_bytes(source, chunk_size, packet_id)
        )
    yield "FINISH", encode_finish()

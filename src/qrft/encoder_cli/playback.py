"""实时二维码播放帧生成器：惰性读取文件，不预生成整批图片。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from qrft.core.manifest import inspect_file, selected_ranges
from qrft.core.protocol import encode_data, encode_finish, encode_start
from qrft.core.protocol_v2 import encode_data_v2, encode_finish_v2, encode_start_v2


def iter_encoded_frames(
    source: Path,
    *,
    chunk_size: int | None = None,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    cancelled=None,
    protocol_version: int = 1,
    repeat_controls: bool = True,
) -> Iterator[tuple[str, bytes]]:
    """START、选定 DATA、FINISH；每次迭代仅读取一个数据包。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    if protocol_version not in (1, 2):
        raise ValueError("unsupported protocol")
    chunk_size = chunk_size if chunk_size is not None else (1400 if protocol_version == 2 else 256)
    if protocol_version == 2 and chunk_size != 1400:
        raise ValueError("v2 requires fixed 1400-byte blocks")
    manifest = inspect_file(source, chunk_size, cancelled=cancelled)
    total = int(manifest["total_packets"])
    if start_id < 0 or start_id > total:
        raise ValueError("start_id outside packet range")
    last = total - 1 if end_id is None else end_id
    if last < -1 or last >= total or (last < start_id and not (total == 0 and last == -1)):
        raise ValueError("end_id outside packet range")
    ranges = selected_ranges(
        total, start_id=start_id, end_id=last, retransmit=retransmit, cancelled=cancelled
    )
    encoder = encode_data_v2 if protocol_version == 2 else encode_data
    start = encode_start_v2(manifest) if protocol_version == 2 else encode_start(manifest)
    finish = encode_finish_v2() if protocol_version == 2 else encode_finish()
    repeats = 20 if protocol_version == 2 and repeat_controls else 1
    for _ in range(repeats):
        if cancelled is not None and cancelled():
            return
        yield "START", start
    with source.open("rb") as stream:
        for first, end in ranges:
            stream.seek(first * chunk_size)
            for packet_id in range(first, end + 1):
                if cancelled is not None and cancelled():
                    return
                payload = stream.read(chunk_size)
                if not payload:
                    raise ValueError("source changed during encoding")
                yield f"{packet_id:08d}", encoder(packet_id, payload)
    for _ in range(repeats):
        if cancelled is not None and cancelled():
            return
        yield "FINISH", finish

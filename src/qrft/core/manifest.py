"""File streaming and retransmission packet selection."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .protocol import FINISH_ID, START_ID, ProtocolError


def inspect_file(path: Path, chunk_size: int) -> dict[str, object]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    size = path.stat().st_size
    total = (size + chunk_size - 1) // chunk_size
    if total > START_ID:
        raise ProtocolError("file requires reserved or unavailable packet IDs")
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    return {
        "version": 1,
        "filename": path.name,
        "file_size": size,
        "chunk_size": chunk_size,
        "total_packets": total,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
        "file_id": sha256.hexdigest()[:32],
    }


def parse_packet_list(text: str, total: int) -> list[int]:
    selected: set[int] = set()
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("-")
        if len(parts) not in (1, 2) or any(
            not part.isascii() or not part.isdecimal() or len(part) > 8 for part in parts
        ):
            raise ProtocolError(f"invalid packet list entry at line {line_number}")
        start = int(parts[0])
        end = int(parts[-1])
        if start > end or end >= total:
            raise ProtocolError(f"packet range out of bounds at line {line_number}")
        if start <= START_ID <= end or start <= FINISH_ID <= end:
            raise ProtocolError("reserved packet ID in selection")
        selected.update(range(start, end + 1))
    return sorted(selected)


def packet_bytes(path: Path, chunk_size: int, packet_id: int) -> bytes:
    if packet_id < 0 or packet_id in (START_ID, FINISH_ID):
        raise ProtocolError("invalid data packet ID")
    with path.open("rb") as stream:
        stream.seek(packet_id * chunk_size)
        payload = stream.read(chunk_size)
    if not payload:
        raise ProtocolError("packet outside file")
    return payload

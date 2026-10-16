"""File streaming and retransmission packet selection."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from .protocol import CHUNK_SIZE, FINISH_ID, START_ID, ProtocolError, validate_chunk_size


def inspect_file(path: Path, chunk_size: int = CHUNK_SIZE, *, cancelled=None) -> dict[str, object]:
    validate_chunk_size(chunk_size)
    size = path.stat().st_size
    total = (size + chunk_size - 1) // chunk_size
    if total > START_ID:
        raise ProtocolError("file requires reserved or unavailable packet IDs")
    md5 = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            if cancelled is not None and cancelled():
                raise InterruptedError("operation cancelled")
            md5.update(block)
    return {
        "version": 2,
        "filename": path.name,
        "file_size": None,
        "chunk_size": chunk_size,
        "total_packets": total,
        "md5": md5.hexdigest().upper(),
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
    validate_chunk_size(chunk_size)
    if type(packet_id) is not int or not 0 <= packet_id < START_ID:
        raise ProtocolError("invalid data packet ID")
    with path.open("rb") as stream:
        stream.seek(packet_id * chunk_size)
        payload = stream.read(chunk_size)
    if not payload:
        raise ProtocolError("packet outside file")
    return payload


def selected_ranges(total, *, start_id=0, end_id=None, retransmit=None, cancelled=None):
    """External-sort missing entries without expanding ranges into a packet-ID set."""
    last = total - 1 if end_id is None else end_id
    if start_id < 0 or start_id > total or last < -1 or last >= total:
        raise ProtocolError("packet selection outside manifest")
    if last < start_id and not (total == 0 and last == -1):
        raise ProtocolError("invalid packet selection range")
    if retransmit is None:
        if last >= start_id:
            yield start_id, last
        return
    # An unnamed temporary SQLite database is deleted by SQLite on close.
    with closing(sqlite3.connect("")) as db:
        db.execute("PRAGMA cache_size=-2048")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("CREATE TABLE ranges(first INTEGER,last INTEGER,PRIMARY KEY(first,last))")
        with Path(retransmit).open(encoding="utf-8-sig") as stream:
            for number, raw in enumerate(stream, 1):
                if cancelled is not None and cancelled():
                    raise InterruptedError("operation cancelled")
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("-")
                if len(parts) not in (1, 2) or any(
                    not p.isascii() or not p.isdecimal() or len(p) > 8 for p in parts
                ):
                    raise ProtocolError(f"invalid missing entry at line {number}")
                first, end = int(parts[0]), int(parts[-1])
                if first > end or end >= total:
                    raise ProtocolError(f"missing entry outside manifest at line {number}")
                db.execute("INSERT OR IGNORE INTO ranges VALUES (?,?)", (first, end))
        merged = None
        for first, end in db.execute(
            "SELECT first,last FROM ranges WHERE last>=? AND first<=? ORDER BY first,last",
            (start_id, last),
        ):
            first, end = max(first, start_id), min(end, last)
            if merged is not None and first <= merged[1] + 1:
                merged = (merged[0], max(merged[1], end))
            else:
                if merged is not None:
                    yield merged
                merged = (first, end)
        if merged is not None:
            yield merged

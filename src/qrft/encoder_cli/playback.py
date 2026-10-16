"""Lazy V2 playback frames: 20 STARTs, selected DATA, then 20 FINISHes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from qrft.core.protocol import CHUNK_SIZE, validate_chunk_size
from qrft.encoder_cli.archive import DEFAULT_MAX_SOURCE_GIB
from qrft.encoder_cli.source import Source, open_source


def iter_encoded_frames(
    source: Path | Source,
    *,
    chunk_size: int | None = None,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    cancelled=None,
    protocol_version: int = 2,
    repeat_controls: bool = True,
    max_source_gib: int = DEFAULT_MAX_SOURCE_GIB,
    expected_archive_md5: str | None = None,
) -> Iterator[tuple[str, bytes]]:
    if protocol_version != 2:
        raise ValueError("only protocol v2 is supported")
    validate_chunk_size(CHUNK_SIZE if chunk_size is None else chunk_size)
    with open_source(
        source,
        cancelled=cancelled,
        chunk_size=chunk_size,
        max_source_gib=max_source_gib,
        expected_archive_md5=expected_archive_md5,
    ) as prepared:
        ranges = prepared.select(start_id=start_id, end_id=end_id, retransmit=retransmit)
        yield from prepared.frames(ranges, repeat_controls=repeat_controls)

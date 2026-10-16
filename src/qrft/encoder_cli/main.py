"""Export a file or RAM folder ZIP as ordered V2 PNG frames."""

from __future__ import annotations

import json
from pathlib import Path

from qrft.core.protocol import encode_finish_v2, encode_start_v2
from qrft.core.qr_image import render_png
from qrft.encoder_cli.archive import DEFAULT_MAX_SOURCE_GIB
from qrft.encoder_cli.source import Source, check_cancel, open_source


def export_frames(
    source: Path | Source,
    output: Path,
    *,
    chunk_size: int | None = None,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    qr_options: dict | None = None,
    cancelled=None,
    protocol_version: int = 2,
    progress=None,
    max_source_gib: int = DEFAULT_MAX_SOURCE_GIB,
    expected_archive_md5: str | None = None,
) -> dict[str, object]:
    """Export each control once; playback repeats controls without duplicate PNGs."""
    if protocol_version != 2:
        raise ValueError("only protocol v2 is supported")
    with open_source(
        source,
        cancelled=cancelled,
        chunk_size=chunk_size,
        max_source_gib=max_source_gib,
        expected_archive_md5=expected_archive_md5,
    ) as prepared:
        prepared.check_output(output)
        ranges = prepared.select(start_id=start_id, end_id=end_id, retransmit=retransmit)
        selected = sum(last - first + 1 for first, last in ranges)
        options = {"protocol_version": 2, **(qr_options or {})}
        # Validate control QR capacity before creating output resources.
        controls = {
            "START": render_png(encode_start_v2(prepared.metadata), **options),
            "FINISH": render_png(encode_finish_v2(), **options),
        }
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        count = 0
        frames = prepared.frames(ranges, repeat_controls=False)
        try:
            for packet_id, raw in frames:
                check_cancel(cancelled)
                if packet_id == "START":
                    name = "00000000-start.png"
                elif packet_id == "FINISH":
                    name = "99999999-finish.png"
                else:
                    name = f"{packet_id}-data.png"
                    count += 1
                png = controls.get(packet_id)
                if png is None:
                    png = render_png(raw, **options)
                with (output / name).open("xb") as stream:
                    stream.write(png)
                if progress is not None:
                    progress(count, selected)
        finally:
            frames.close()
        check_cancel(cancelled)
        summary = {
            **prepared.describe(),
            "exported_data_packets": count,
            "retransmission": retransmit is not None,
            "ranges": ranges,
            "control_repeats": 1,
        }
        with (output / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return summary


def main(argv: list[str] | None = None) -> int:
    import sys

    from qrft.encoder_cli.entrypoint import main as console_main

    return console_main(["export", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())

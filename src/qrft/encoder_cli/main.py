"""二维码编码器命令行入口：导出按序编号的 PNG 帧。"""

from __future__ import annotations

import json
from pathlib import Path

from qrft.core.protocol import decode_frame
from qrft.core.qr_image import render_png
from qrft.encoder_cli.playback import iter_encoded_frames


def export_frames(
    source: Path,
    output: Path,
    *,
    chunk_size: int | None = None,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    qr_options: dict | None = None,
    cancelled=None,
    protocol_version: int = 1,
    progress=None,
) -> dict[str, object]:
    """流式导出 PNG，不把整个文件或所有二维码载入内存。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)
    manifest = None
    count = 0
    selected = 0
    for packet_id, raw in iter_encoded_frames(
        source,
        chunk_size=chunk_size,
        retransmit=retransmit,
        start_id=start_id,
        end_id=end_id,
        cancelled=cancelled,
        protocol_version=protocol_version,
        repeat_controls=False,
    ):
        if cancelled is not None and cancelled():
            raise InterruptedError("export cancelled")
        frame = decode_frame(raw)
        if frame.kind == "start":
            manifest = frame.metadata
            from qrft.core.manifest import selected_ranges

            selected = sum(
                last - first + 1
                for first, last in selected_ranges(
                    manifest["total_packets"],
                    start_id=start_id,
                    end_id=end_id,
                    retransmit=retransmit,
                    cancelled=cancelled,
                )
            )
            name = "00000000-start.png"
        elif frame.kind == "finish":
            name = "99999999-finish.png"
        else:
            name = f"{packet_id}-data.png"
            count += 1
        png = render_png(raw, protocol_version=protocol_version, **(qr_options or {}))
        with (output / name).open("xb") as stream:
            stream.write(png)
        if progress is not None:
            progress(count, selected)
    if cancelled is not None and cancelled():
        raise InterruptedError("export cancelled")
    summary = {**manifest, "exported_data_packets": count, "retransmission": retransmit is not None}
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    import sys

    from qrft.encoder_cli.entrypoint import main as console_main

    return console_main(["export", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())

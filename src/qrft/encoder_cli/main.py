"""二维码编码器命令行入口：导出按序编号的 PNG 帧。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qrft.core.protocol import decode_frame
from qrft.core.qr_image import qr_png
from qrft.encoder_cli.playback import iter_encoded_frames


def export_frames(
    source: Path,
    output: Path,
    *,
    chunk_size: int = 256,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    qr_options: dict | None = None,
    cancelled=None,
) -> dict[str, object]:
    """流式导出 PNG，不把整个文件或所有二维码载入内存。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)
    manifest = None
    count = 0
    for packet_id, raw in iter_encoded_frames(
        source,
        chunk_size=chunk_size,
        retransmit=retransmit,
        start_id=start_id,
        end_id=end_id,
        cancelled=cancelled,
    ):
        if cancelled is not None and cancelled():
            raise InterruptedError("export cancelled")
        frame = decode_frame(raw)
        if frame.kind == "start":
            manifest = frame.metadata
            name = "00000000-start.png"
        elif frame.kind == "finish":
            name = "99999999-finish.png"
        else:
            name = f"{packet_id}-data.png"
            count += 1
        png = qr_png(raw, **(qr_options or {}))
        with (output / name).open("xb") as stream:
            stream.write(png)
    if cancelled is not None and cancelled():
        raise InterruptedError("export cancelled")
    summary = {**manifest, "exported_data_packets": count, "retransmission": retransmit is not None}
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 二进制文件二维码帧导出")
    parser.add_argument("source", type=Path, help="待编码文件路径")
    parser.add_argument("--output", type=Path, required=True, help="二维码 PNG 输出目录")
    parser.add_argument("--chunk-size", type=int, default=256, help="每包数据字节数（默认 256）")
    parser.add_argument("--retransmit", type=Path, help="缺包列表 TXT 文件，指定后仅导出所列包")
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--end-id", type=int)
    parser.add_argument("--correction", choices=["L", "M", "Q", "H"], default="M")
    parser.add_argument("--box-size", type=int, default=8)
    args = parser.parse_args(argv)
    result = export_frames(
        args.source,
        args.output,
        chunk_size=args.chunk_size,
        retransmit=args.retransmit,
        start_id=args.start_id,
        end_id=args.end_id,
        qr_options={"correction": args.correction, "box_size": args.box_size},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

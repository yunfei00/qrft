"""二维码编码器命令行入口：导出按序编号的 PNG 帧。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qrft.core.manifest import inspect_file, packet_bytes, parse_packet_list
from qrft.core.protocol import encode_data, encode_finish, encode_start
from qrft.core.qr_image import save_qr_png


def export_frames(
    source: Path,
    output: Path,
    *,
    chunk_size: int = 256,
    retransmit: Path | None = None,
) -> dict[str, object]:
    """流式导出 PNG，不把整个文件或所有二维码载入内存。"""
    if not source.is_file():
        raise FileNotFoundError(source)
    manifest = inspect_file(source, chunk_size)
    total = int(manifest["total_packets"])
    output.mkdir(parents=True, exist_ok=True)

    if retransmit is None:
        ids = range(total)
    else:
        ids = parse_packet_list(retransmit.read_text(encoding="utf-8-sig"), total)

    save_qr_png(encode_start(manifest), output / "00000000-start.png")
    count = 0
    for packet_id in ids:
        payload = packet_bytes(source, chunk_size, packet_id)
        save_qr_png(encode_data(packet_id, payload), output / f"{packet_id:08d}-data.png")
        count += 1
    save_qr_png(encode_finish(), output / "99999999-finish.png")
    summary = {**manifest, "exported_data_packets": count, "retransmission": retransmit is not None}
    (output / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 二进制文件二维码帧导出")
    parser.add_argument("source", type=Path, help="待编码文件路径")
    parser.add_argument("--output", type=Path, required=True, help="二维码 PNG 输出目录")
    parser.add_argument("--chunk-size", type=int, default=256, help="每包数据字节数（默认 256）")
    parser.add_argument("--retransmit", type=Path, help="缺包列表 TXT 文件，指定后仅导出所列包")
    args = parser.parse_args(argv)
    result = export_frames(
        args.source, args.output, chunk_size=args.chunk_size, retransmit=args.retransmit
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

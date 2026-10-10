"""Windows 编码器 EXE 入口：统一 PNG 导出与全屏播放。"""

from __future__ import annotations

import argparse
from pathlib import Path

from qrft.encoder_cli.main import main as export_main
from qrft.encoder_cli.player import play


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 编码器")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="将文件导出为二维码 PNG")
    export.add_argument("source", type=Path)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--chunk-size", type=int, default=256)
    export.add_argument("--retransmit", type=Path)
    player = sub.add_parser("play", help="全屏实时播放二维码")
    player.add_argument("source", type=Path)
    player.add_argument("--chunk-size", type=int, default=256)
    player.add_argument("--interval-ms", type=int, default=300)
    player.add_argument("--initial-delay-ms", type=int, default=3000)
    player.add_argument("--retransmit", type=Path)
    player.add_argument("--start-id", type=int, default=0)
    player.add_argument("--end-id", type=int)
    player.add_argument("--workers", type=int, default=2)
    player.add_argument("--prefetch", type=int, default=4)
    player.add_argument("--windowed", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "export":
        options = [
            str(args.source),
            "--output",
            str(args.output),
            "--chunk-size",
            str(args.chunk_size),
        ]
        if args.retransmit is not None:
            options.extend(["--retransmit", str(args.retransmit)])
        return export_main(options)
    return play(
        args.source,
        chunk_size=args.chunk_size,
        interval_ms=args.interval_ms,
        initial_delay_ms=args.initial_delay_ms,
        retransmit=args.retransmit,
        start_id=args.start_id,
        end_id=args.end_id,
        workers=args.workers,
        prefetch=args.prefetch,
        fullscreen=not args.windowed,
    )


if __name__ == "__main__":
    raise SystemExit(main())

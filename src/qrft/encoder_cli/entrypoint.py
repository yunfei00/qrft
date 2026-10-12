"""Windows 编码器 EXE 入口：统一 PNG 导出与全屏播放。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qrft.encoder_cli.main import main as export_main
from qrft.encoder_cli.player import play


def main(argv: list[str] | None = None) -> int:
    """兼容 Windows 非 UTF-8 控制台中的中文帮助与 JSON 输出。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="QRFT 编码器")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="将文件导出为二维码 PNG")
    export.add_argument("source", type=Path)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    export.add_argument("--chunk-size", type=int)
    export.add_argument("--retransmit", type=Path)
    export.add_argument("--start-id", type=int, default=0)
    export.add_argument("--end-id", type=int)
    export.add_argument("--correction", choices=["L", "M", "Q", "H"])
    export.add_argument("--box-size", type=int)
    player = sub.add_parser("play", help="全屏实时播放二维码")
    player.add_argument("source", type=Path)
    player.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    player.add_argument("--player", choices=["qt", "opencv"], default="qt")
    player.add_argument("--chunk-size", type=int)
    player.add_argument("--interval-ms", type=int)
    player.add_argument("--initial-delay-ms", type=int, default=3000)
    player.add_argument("--retransmit", type=Path)
    player.add_argument("--start-id", type=int, default=0)
    player.add_argument("--end-id", type=int)
    player.add_argument("--workers", type=int, default=2)
    player.add_argument("--prefetch", type=int, default=4)
    player.add_argument("--windowed", action="store_true")
    player.add_argument("--exit-when-finished", action="store_true", help="播放全部包后自动退出")
    args = parser.parse_args(argv)
    if args.command == "export":
        options = [
            str(args.source),
            "--output",
            str(args.output),
            "--protocol",
            args.protocol,
        ]
        if args.retransmit is not None:
            options.extend(["--retransmit", str(args.retransmit)])
        options.extend(
            [
                "--start-id",
                str(args.start_id),
            ]
        )
        for key in ("chunk_size", "correction", "box_size"):
            value = getattr(args, key)
            if value is not None:
                options.extend(["--" + key.replace("_", "-"), str(value)])
        if args.end_id is not None:
            options.extend(["--end-id", str(args.end_id)])
        return export_main(options)
    if args.player == "opencv":
        from qrft.encoder_cli.opencv_player import play_opencv

        return play_opencv(
            args.source,
            protocol_version=2 if args.protocol == "v2" else 1,
            chunk_size=args.chunk_size,
            interval_ms=args.interval_ms,
            initial_delay_ms=args.initial_delay_ms,
            retransmit=args.retransmit,
            start_id=args.start_id,
            end_id=args.end_id,
        )
    return play(
        args.source,
        protocol_version=2 if args.protocol == "v2" else 1,
        chunk_size=args.chunk_size,
        interval_ms=args.interval_ms,
        initial_delay_ms=args.initial_delay_ms,
        retransmit=args.retransmit,
        start_id=args.start_id,
        end_id=args.end_id,
        workers=args.workers,
        prefetch=args.prefetch,
        fullscreen=not args.windowed,
        exit_when_finished=args.exit_when_finished,
    )


if __name__ == "__main__":
    raise SystemExit(main())

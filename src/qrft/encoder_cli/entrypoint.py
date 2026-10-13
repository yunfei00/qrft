"""Independent encoder console: authenticate first, then export or explicitly play."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qrft.encoder_cli.access import SilentArgumentParserMixin, authenticate


class CommandParser(SilentArgumentParserMixin, argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.update(add_help=False, allow_abbrev=False)
        super().__init__(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    if not authenticate():
        return 1
    if not (sys.argv[1:] if argv is None else argv):
        print("QRFT 编码器：export 导出 PNG；play 打开独立播放器。参数见 docs/V2_USER_GUIDE.md。")
        return 0
    parser = CommandParser()
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
    player = sub.add_parser("play")
    player.add_argument("source", type=Path)
    player.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    player.add_argument("--player", choices=["qt", "opencv"], default="qt")
    player.add_argument("--chunk-size", type=int)
    player.add_argument("--interval-ms", type=int)
    player.add_argument("--initial-delay-ms", type=int, default=0)
    player.add_argument("--retransmit", type=Path)
    player.add_argument("--start-id", type=int, default=0)
    player.add_argument("--end-id", type=int)
    player.add_argument("--workers", type=int, default=2)
    player.add_argument("--prefetch", type=int, default=4)
    player.add_argument("--windowed", action="store_true")
    player.add_argument("--fullscreen", action="store_true")
    player.add_argument("--exit-when-finished", action="store_true", help="播放全部包后自动退出")
    try:
        args = parser.parse_args(argv)
        return execute(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def execute(args) -> int:
    if args.command == "export":
        from qrft.encoder_cli.main import export_frames

        result = export_frames(
            args.source,
            args.output,
            protocol_version=2 if args.protocol == "v2" else 1,
            chunk_size=args.chunk_size,
            retransmit=args.retransmit,
            start_id=args.start_id,
            end_id=args.end_id,
            qr_options={
                k: v
                for k, v in {"correction": args.correction, "box_size": args.box_size}.items()
                if v is not None
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
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
            fullscreen=args.fullscreen and not args.windowed,
            exit_when_finished=args.exit_when_finished,
        )
    from qrft.encoder_cli.player import play

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
        fullscreen=args.fullscreen and not args.windowed,
        exit_when_finished=args.exit_when_finished,
    )


if __name__ == "__main__":
    raise SystemExit(main())

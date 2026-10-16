"""Terminal-gated encoder CLI: inspect, export or play a V2 file/folder source."""

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
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print("QRFT 编码器：info 检查；export 导出 PNG；play 播放二维码。参数见 README.md。")
        return 0
    parser = CommandParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("info", "export", "play"):
        sub = commands.add_parser(command)
        sub.add_argument("source", type=Path)
        sub.add_argument("--chunk-size", type=int, help="每包字节数，默认 2100，范围 1..2124")
        sub.add_argument("--max-archive-mib", type=int, default=128)
        sub.add_argument("--expected-archive-md5")
        sub.add_argument("--protocol", choices=["v2"], default="v2")
        if command != "info":
            sub.add_argument("--start-id", type=int, default=0)
            sub.add_argument("--end-id", type=int)
            sub.add_argument("--retransmit", "--missing", dest="retransmit", type=Path)
        if command == "export":
            sub.add_argument("--output", type=Path, required=True)
        if command == "play":
            sub.add_argument("--interval-ms", type=int, default=50)
            sub.add_argument("--fullscreen", action="store_true")
            sub.add_argument("--workers", type=int, default=2)
            sub.add_argument("--prefetch", type=int, default=4)
            sub.add_argument("--exit-when-finished", action="store_true")
    try:
        args = parser.parse_args(arguments)
        return execute(args)
    except (KeyboardInterrupt, InterruptedError):
        print("操作已取消，保留本次输出。", file=sys.stderr)
        return 130
    except MemoryError:
        print("内存不足，请减小文件夹或内存预算；文件夹 ZIP 仅在内存中生成。", file=sys.stderr)
        return 2
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def execute(args) -> int:
    from qrft.core.protocol import encode_start_v2
    from qrft.core.qr_image import render_png
    from qrft.encoder_cli.source import Source

    with Source(
        args.source,
        chunk_size=args.chunk_size,
        max_archive_mib=args.max_archive_mib,
        expected_archive_md5=args.expected_archive_md5,
    ) as source:
        if args.command == "info":
            render_png(encode_start_v2(source.metadata), protocol_version=2)
            print(json.dumps(source.describe(), ensure_ascii=False, indent=2))
            return 0
        options = {
            "retransmit": args.retransmit,
            "start_id": args.start_id,
            "end_id": args.end_id,
        }
        source.select(**options)
        if args.command == "export":
            from qrft.encoder_cli.main import export_frames

            result = export_frames(source, args.output, **options)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        from qrft.encoder_cli.opencv_player import play_opencv

        return play_opencv(
            source,
            interval_ms=args.interval_ms,
            fullscreen=args.fullscreen,
            exit_when_finished=args.exit_when_finished,
            workers=args.workers,
            prefetch=args.prefetch,
            **options,
        )


if __name__ == "__main__":
    raise SystemExit(main())

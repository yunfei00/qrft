"""Development encoder CLI with usage help for inspecting, exporting and playback."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qrft.encoder_cli.access import authenticate


class CommandParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.update(allow_abbrev=False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        self.print_usage(sys.stderr)
        raise ValueError(message)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    if not authenticate():
        return 1
    arguments = sys.argv[1:] if argv is None else argv
    parser = CommandParser(
        prog="QRFT-Encoder-CLI" if getattr(sys, "frozen", False) else "qrft encode",
        description="QRFT v2 编码器：研发阶段暂不校验口令，可直接从命令行或脚本运行。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例：
  qrft encode info "D:\\Data\\example.bin"
  qrft encode play "D:\\Data\\example.bin" --chunk-size 2100
  qrft encode export "D:\\Data\\ExampleFolder" --output "D:\\QRFT\\frames"
  qrft encode play "D:\\Data\\example.bin" --missing "D:\\QRFT\\missing.txt"

也可使用 python -m qrft encode 或 QRFT-Encoder-CLI.exe，后接相同子命令。
默认每包 2100 字节；补传须使用与首次传输相同的分块大小。
播放窗口：Space 开始/暂停/继续，Esc 结束。使用 <子命令> --help 查看参数。""",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command, description in (
        ("info", "检查文件或文件夹，显示分块数量、MD5 和目录 ZIP 信息"),
        ("export", "导出二维码 PNG 和 manifest.json；输出目录必须尚不存在"),
        ("play", "播放二维码供录屏；Space 开始/暂停/继续，Esc 结束"),
    ):
        sub = commands.add_parser(command, help=description, description=description)
        sub.add_argument("source", type=Path, help="待传输的文件或文件夹路径")
        sub.add_argument("--chunk-size", type=int, help="每包字节数，默认 2100，范围 1..2124")
        sub.add_argument(
            "--max-archive-mib", type=int, default=128, help="目录 ZIP 内存上限，默认 128 MiB"
        )
        sub.add_argument("--expected-archive-md5", help="目录补传必填：首次传输的 ZIP MD5")
        sub.add_argument("--protocol", choices=["v2"], default="v2", help="仅支持 v2 协议")
        if command != "info":
            sub.add_argument("--start-id", type=int, default=0, help="起始 DATA 包号，包含，默认 0")
            sub.add_argument("--end-id", type=int, help="结束 DATA 包号，包含，默认最后一包")
            sub.add_argument(
                "--retransmit",
                "--missing",
                dest="retransmit",
                type=Path,
                help="缺包 TXT 清单路径，支持包号或闭区间",
            )
        if command == "export":
            sub.add_argument(
                "--output", type=Path, required=True, help="二维码 PNG 输出目录，不能已存在"
            )
        if command == "play":
            sub.add_argument(
                "--interval-ms", type=int, default=50, help="DATA 展示间隔，默认 50 毫秒"
            )
            sub.add_argument("--fullscreen", action="store_true", help="全屏显示，默认窗口模式")
            sub.add_argument("--workers", type=int, default=2, help="二维码生成线程数，默认 2")
            sub.add_argument(
                "--prefetch", type=int, default=4, help="预生成队列容量，须不小于 workers，默认 4"
            )
            sub.add_argument(
                "--exit-when-finished",
                action="store_true",
                help="播放结束后自动退出，默认保留结束画面",
            )
    if not arguments:
        parser.print_help()
        return 0
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

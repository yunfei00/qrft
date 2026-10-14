"""Silent terminal gate, then independent QRFT2100 commands. Never import Qt."""

from __future__ import annotations

import argparse
import getpass
import hmac
import json
import sys
import warnings
from pathlib import Path


def authenticate():
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print("拒绝访问：需要可交互终端。", file=sys.stderr)
        return False
    for _ in range(3):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                entered = getpass.getpass("")
            if hmac.compare_digest(entered.encode("utf-8"), b"qsnfj"):
                return True
        except (KeyboardInterrupt, EOFError, OSError, UnicodeError, getpass.GetPassWarning):
            print("校验已取消。", file=sys.stderr)
            return False
        print("校验未通过。", file=sys.stderr)
    print("三次校验失败，已拒绝访问。", file=sys.stderr)
    return False


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **{**kwargs, "add_help": False, "allow_abbrev": False})

    def error(self, message):
        raise ValueError("参数无效；请参考 docs/ENCODER_2100_USER_GUIDE.md。")


def main(argv=None):
    if not authenticate():
        return 1
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print("QRFT2100：info 文件检查；export PNG 导出；play 独立播放。参数见操作手册。")
        return 0
    parser = Parser()
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("info", "export", "play"):
        sub = commands.add_parser(command)
        sub.add_argument("source", type=Path)
        sub.add_argument("--max-archive-mib", type=int, default=128)
        sub.add_argument("--expected-archive-md5")
        if command != "info":
            sub.add_argument("--start-id", type=int, default=0)
            sub.add_argument("--end-id", type=int)
            sub.add_argument("--missing", type=Path)
        if command == "export":
            sub.add_argument("--output", type=Path, required=True)
        if command == "play":
            sub.add_argument("--interval-ms", type=int, default=50)
            sub.add_argument("--fullscreen", action="store_true")
            sub.add_argument("--prefetch", type=int, default=4)
            sub.add_argument(
                "--workers", type=int, help="二维码生成工作进程数（默认自动，最多3个）"
            )
            sub.add_argument("--log", type=Path, help="可选：显式启用本地诊断日志；默认不写入")
    source = None
    try:
        args = parser.parse_args(arguments)
        from .encoder import Source, export, select

        source = Source(
            args.source,
            max_archive_mib=args.max_archive_mib,
            expected_archive_md5=args.expected_archive_md5,
        )
        if args.command == "info":
            from .qr import qr_code

            qr_code(source.metadata.start())
            print(json.dumps(source.describe(), ensure_ascii=False, indent=2))
            return 0
        ranges = select(source.metadata.packets, args.start_id, args.end_id, args.missing)
        if (
            source.archive_details is not None
            and args.expected_archive_md5 is None
            and (args.missing is not None or args.start_id != 0 or args.end_id is not None)
        ):
            raise ValueError(
                "Folder retransmission requires --expected-archive-md5 from original task"
            )
        if source.archive_details is not None:
            print(f"Folder Content MD5: {source.archive_details['folder_content_md5']}")
            print(f"Archive ZIP MD5: {source.metadata.md5}")
            print(
                f"ZIP Size: {source.metadata.size} bytes | DATA Packets: {source.metadata.packets}"
            )
        if args.command == "export":
            result = export(source, args.output, ranges)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print(f"操作日志：{args.output / 'operations.jsonl'}")
            return 0
        from .player import play

        return play(
            source,
            ranges,
            log_path=args.log,
            interval_ms=args.interval_ms,
            fullscreen=args.fullscreen,
            capacity=args.prefetch,
            workers=args.workers,
        )
    except (KeyboardInterrupt, InterruptedError):
        print("操作已取消，保留本次输出。", file=sys.stderr)
        return 130
    except MemoryError:
        print(
            "RAM allocation failed; reduce archive size or memory budget. No disk fallback.",
            file=sys.stderr,
        )
        return 2
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 2
    finally:
        if source is not None:
            source.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""One entry point for encoding, decoding, merging and scheduling."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "encode":
        from qrft.encoder_cli.entrypoint import main as encode

        return encode(args[1:])
    if args and args[0] == "control":
        from qrft.control.app import main as control

        return control(args[1:])
    if args and args[0] == "worker":
        from qrft.decoder.worker import main as worker

        return worker(args[1:])
    if args and args[0] == "decode":
        if len(args) > 1 and not args[1].startswith("-"):
            from qrft.single_decoder.main import main as decode_project

            return decode_project(args)
        from qrft.decoder_gui.main import main as decode_gui

        return decode_gui(args[1:])

    parser = argparse.ArgumentParser(description="QRFT：编码、解码、合并与调度（仅 v2）")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("encode", help="CLI 编码：info / export / play")
    commands.add_parser("decode", help="打开解码界面；提供项目目录时批量解码")
    merge = commands.add_parser("merge", help="合并项目已解出的包并校验文件，不扫描视频")
    merge.add_argument("project", type=Path)
    merge.add_argument("--max-folder-bytes", type=int, default=8 * 1024**3)
    commands.add_parser("control", help="启动调度中心 Web 界面")
    commands.add_parser("worker", help="启动分布式解码节点")
    options = parser.parse_args(args)
    if options.command == "merge":
        from qrft.single_decoder.project import merge_project

        try:
            result = merge_project(options.project, max_folder_bytes=options.max_folder_bytes)
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"合并失败：{exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "SUCCESS" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

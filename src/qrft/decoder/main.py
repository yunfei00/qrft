"""从录屏视频恢复 QRFT 文件的本地命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qrft.core.reassemble import FileAssembler
from qrft.decoder.video import iter_video_frames


def restore_video(
    video: Path,
    output: Path,
    *,
    sample_fps: float = 10.0,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> Path | None:
    assembler = FileAssembler(output)
    for frame in iter_video_frames(
        video,
        sample_fps=sample_fps,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    ):
        assembler.accept(frame)
    return assembler.finalize()


def main(argv: list[str] | None = None) -> int:
    """兼容 Windows 非 UTF-8 控制台的中文输出。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="QRFT 录屏视频文件恢复")
    parser.add_argument("video", type=Path, help="视频路径，可为可访问的 SMB 路径")
    parser.add_argument("--output", required=True, type=Path, help="恢复文件输出目录")
    parser.add_argument("--sample-fps", type=float, default=10.0)
    parser.add_argument("--start", type=float, default=0.0, help="起始秒数")
    parser.add_argument("--end", type=float, help="结束秒数")
    args = parser.parse_args(argv)
    restored = restore_video(
        args.video,
        args.output,
        sample_fps=args.sample_fps,
        start_seconds=args.start,
        end_seconds=args.end,
    )
    if restored is None:
        print("未完成恢复；请查看输出目录中的 missing.txt、missing.csv、missing.json")
        return 2
    print(f"恢复成功：{restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

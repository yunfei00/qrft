"""从录屏视频恢复 QRFT 文件的本地命令行入口。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from qrft.control.packets import ingest, init_schema, lock_protocol
from qrft.control.recovery import recover
from qrft.control.session import bind_start, init_session
from qrft.core.protocol import ProtocolError, decode_frame, serialize_frame
from qrft.core.validation import validate_data
from qrft.decoder.video import iter_video_frames


def restore_video(
    video: Path | list[Path],
    output: Path,
    *,
    sample_fps: float = 60.0,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
    protocol_version: int | None = None,
) -> Path | None:
    """Explicit output directory is one durable task, including all retransmission videos."""
    output.mkdir(parents=True, exist_ok=True)
    session = output / ".qrft-session"
    if protocol_version not in (None, 1, 2):
        raise ValueError("unsupported protocol")
    marker = "QRFT local video task; one file and one protocol only\n"
    if session.exists():
        if (
            session.is_symlink()
            or session.resolve().parent != output.resolve()
            or not (session / "OWNER.txt").is_file()
            or ((session / "OWNER.txt").read_text() != marker)
        ):
            raise ProtocolError("unsafe or unrelated local task directory")
    else:
        for name in ("missing.txt", "missing.csv", "missing.json", "verification.json"):
            if (output / name).exists():
                raise FileExistsError(f"已有文件不能覆盖，请为任务选择新目录：{output / name}")
        session.mkdir()
        (session / "OWNER.txt").write_text(marker)
    database = session / "receipts.sqlite3"
    if database.is_symlink():
        raise ProtocolError("unsafe local task database")
    videos = [video] if isinstance(video, Path) else video
    with closing(sqlite3.connect(database)) as db:
        db.row_factory = sqlite3.Row
        init_schema(db)
        init_session(db)
        if protocol_version is not None:
            lock_protocol(db, 1, protocol_version)
        db.commit()
        for path in videos:
            for frame in iter_video_frames(
                path, sample_fps=sample_fps, start_seconds=start_seconds, end_seconds=end_seconds
            ):
                with db:
                    lock_protocol(db, 1, frame.version)
                    raw = serialize_frame(frame)
                    if frame.kind == "start":
                        bind_start(db, 1, raw)
                    elif frame.kind == "finish":
                        db.execute("INSERT OR IGNORE INTO task_finishes VALUES (1)")
                    else:
                        meta = db.execute(
                            "SELECT start_frame FROM task_manifests WHERE task_id=1"
                        ).fetchone()
                        if meta is not None:
                            validate_data(decode_frame(bytes(meta[0])).metadata, frame)
                        ingest(db, 1, raw)
        if not db.execute("SELECT 1 FROM task_manifests WHERE task_id=1").fetchone():
            with (session / "status.json").open("w", encoding="utf-8") as stream:
                json.dump({"status": "awaiting_start", "missing_ids": None}, stream)
            return None
        version = db.execute("SELECT version FROM task_protocols WHERE task_id=1").fetchone()[0]
        result = recover(db, 1, output, files_subdirectory=version == 2)
        evidence = output / "verification.json" if version == 2 else session / "verification.json"
        with evidence.open("w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        return Path(result["path"]) if result["status"] == "verified" else None


def main(argv: list[str] | None = None) -> int:
    """兼容 Windows 非 UTF-8 控制台的中文输出。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="QRFT 录屏视频文件恢复")
    parser.add_argument(
        "video", type=Path, nargs="+", help="同一任务的视频及补传视频，本地或 SMB 路径"
    )
    parser.add_argument("--output", required=True, type=Path, help="恢复文件输出目录")
    parser.add_argument(
        "--sample-fps", type=float, default=60.0, help="默认60，避免漏掉50ms DATA；低于20不适合v2"
    )
    parser.add_argument("--protocol", choices=["auto", "v1", "v2"], default="auto")
    parser.add_argument("--start", type=float, default=0.0, help="起始秒数")
    parser.add_argument("--end", type=float, help="结束秒数")
    args = parser.parse_args(argv)
    restored = restore_video(
        args.video,
        args.output,
        sample_fps=args.sample_fps,
        start_seconds=args.start,
        end_seconds=args.end,
        protocol_version={"auto": None, "v1": 1, "v2": 2}[args.protocol],
    )
    if restored is None:
        print("未完成恢复；请查看输出目录中的 missing.txt、missing.csv、missing.json")
        return 2
    print(f"恢复成功：{restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""English project decoder CLI; no encoder gate, GUI, server or Worker required."""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from .project import decode_project


class Progress:
    def __init__(self):
        self.last = float("-inf")

    def __call__(self, number, count, status, index, total):
        moment = time.monotonic()
        if status == "processing" and moment - self.last < 5:
            return
        self.last = moment
        percent = f"{100 * index / total:.1f}%" if total else f"frames {index}"
        print(
            f"[{time.strftime('%H:%M:%S')}] VIDEO {number}/{count} | {percent} | {status}",
            flush=True,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Single-project V2 / QRFT2100 video decoder")
    parser.add_argument("command", choices=["decode"])
    parser.add_argument("project", type=Path)
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Rescan unchanged completed videos; retain valid receipts",
    )
    parser.add_argument(
        "--max-folder-bytes",
        type=int,
        default=8 * 1024**3,
        help="Maximum uncompressed bytes for folder fingerprint verification (default 8 GiB)",
    )
    args = parser.parse_args(argv)
    try:
        result = decode_project(
            args.project,
            progress=Progress(),
            max_folder_bytes=args.max_folder_bytes,
            rescan=args.rescan,
        )
    except KeyboardInterrupt:
        print("Result: INTERRUPTED", file=sys.stderr)
        return 130
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for label, field in (
        ("Videos", "videos_total"),
        ("Completed", "videos_completed"),
        ("Skipped", "videos_skipped"),
        ("Failed videos", "videos_failed"),
    ):
        print(f"{label}: {result[field]}")
    total = result["total_packets"] if result["total_packets"] is not None else "UNKNOWN"
    print(f"Packets: {result['received_packets']}/{total}")
    print(
        f"Missing: {result['missing_packets'] if result['missing_packets'] is not None else 'UNKNOWN'}"
    )
    print(f"MD5: {'PASS' if result['md5_verified'] else 'NOT VERIFIED'}")
    if result.get("folder", {}).get("status") in ("PASS", "FAILED"):
        print(f"Folder content: {result['folder']['status']}")
    print(f"Result: {result['status']}")
    return 130 if result["interrupted"] else 0 if result["status"] == "SUCCESS" else 2

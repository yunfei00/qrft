"""Reproducible bounded-memory file hashing, SQLite and missing-export benchmark."""

import argparse
import json
import sqlite3
import tempfile
import time
import tracemalloc
from contextlib import closing
from pathlib import Path

from qrft.control.packets import ingest, init_schema
from qrft.core.manifest import inspect_file
from qrft.core.missing import stream_missing
from qrft.core.protocol import encode_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-mib", type=int, default=1024)
    parser.add_argument("--packets", type=int, default=100000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.file_mib < 0 or not 0 <= args.packets <= 1_000_000:
        parser.error("invalid benchmark size")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qrft-benchmark-", dir=args.output.parent) as scratch:
        root = Path(scratch)
        source = root / "binary.bin"
        block = bytes(range(256)) * 4096
        with source.open("xb") as stream:
            for _ in range(args.file_mib):
                stream.write(block)
        tracemalloc.start()
        start = time.perf_counter()
        meta = inspect_file(source, 256)
        hashing_seconds = time.perf_counter() - start
        _, hashing_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        with closing(sqlite3.connect(root / "packets.db")) as db:
            db.row_factory = sqlite3.Row
            init_schema(db)
            db.commit()
            db.execute("BEGIN")
            start = time.perf_counter()
            for packet_id in range(0, args.packets, 2):
                ingest(db, 1, encode_data(packet_id, b"x" * 256))
                if packet_id % 2000 == 0:
                    db.commit()
                    db.execute("BEGIN")
            db.commit()
            ingest_seconds = time.perf_counter() - start
            tracemalloc.start()
            start = time.perf_counter()
            count = stream_missing(
                root / "reports",
                args.packets,
                (
                    row[0]
                    for row in db.execute(
                        "SELECT packet_id FROM packets WHERE task_id=1 ORDER BY packet_id"
                    )
                ),
            )
            export_seconds = time.perf_counter() - start
            _, export_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        result = {
            "file_bytes": meta["file_size"],
            "sha256": meta["sha256"],
            "hashing_seconds": hashing_seconds,
            "hashing_python_peak_bytes": hashing_peak,
            "stored_packets": (args.packets + 1) // 2,
            "ingest_seconds": ingest_seconds,
            "missing_count": count,
            "export_seconds": export_seconds,
            "export_python_peak_bytes": export_peak,
            "limitations": "Python allocations only, excludes native RSS; not a full 1GB QR/video transfer",
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

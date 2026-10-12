"""Recover from durable SQLite packets using bounded file reads and atomic publication."""

import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path

from qrft.core.missing import stream_missing
from qrft.core.protocol import ProtocolError, decode_frame
from qrft.core.reassemble import FileAssembler
from qrft.core.validation import validate_data


def recover(
    db: sqlite3.Connection, task_id: int, directory: Path, *, files_subdirectory=True
) -> dict:
    manifest = db.execute(
        "SELECT start_frame FROM task_manifests WHERE task_id=?", (task_id,)
    ).fetchone()
    if manifest is None:
        raise ProtocolError("START manifest required")
    directory.mkdir(parents=True, exist_ok=True)
    # A crash leaves SQLite intact; a fresh attempt reconstructs the staging file.
    with tempfile.TemporaryDirectory(dir=directory) as staging:
        assembler = FileAssembler(Path(staging))
        assembler.received.close()
        assembler.accept(decode_frame(bytes(manifest["start_frame"])))
        meta = assembler.manifest
        if (
            meta.get("version", 1) == 2
            and db.execute(
                "SELECT 1 FROM packet_conflicts WHERE task_id=? LIMIT 1", (task_id,)
            ).fetchone()
        ):
            raise ProtocolError("v2 packet conflicts require a new isolated task")
        received = 0
        with assembler._file.open("r+b") as output:
            for row in db.execute(
                "SELECT frame FROM packets WHERE task_id=? ORDER BY packet_id", (task_id,)
            ):
                frame = decode_frame(bytes(row["frame"]))
                validate_data(meta, frame)
                output.seek(frame.packet_id * meta["chunk_size"])
                output.write(frame.payload)
                received += 1
            output.flush()
            os.fsync(output.fileno())
        reports = directory
        if not files_subdirectory and meta.get("filename") in {
            "missing.txt",
            "missing.csv",
            "missing.json",
        }:
            reports = directory / ".qrft-missing"
        stream_missing(
            reports,
            meta["total_packets"],
            (
                row[0]
                for row in db.execute(
                    "SELECT packet_id FROM packets WHERE task_id=? ORDER BY packet_id", (task_id,)
                )
            ),
        )
        if received != meta["total_packets"] or (
            meta.get("version", 1) == 1
            and not db.execute("SELECT 1 FROM task_finishes WHERE task_id=?", (task_id,)).fetchone()
        ):
            return {"status": "incomplete"}
        sha = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        with assembler._file.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                sha.update(block)
                md5.update(block)
        if md5.hexdigest().upper() != meta["md5"].upper() or (
            meta.get("version", 1) == 1 and sha.hexdigest().upper() != meta["sha256"].upper()
        ):
            raise ProtocolError("reassembled file hash mismatch")
        filename = meta.get("filename")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or any(ch in filename for ch in '<>:"/\\|?*')
            or any(ord(ch) < 32 for ch in filename)
            or filename.endswith((" ", "."))
            or filename.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
        ):
            raise ProtocolError("unsafe filename")
        files = directory / "files" if files_subdirectory else directory
        files.mkdir(exist_ok=True)
        target = files / filename
        if directory.is_symlink() or (
            files_subdirectory and files.resolve().parent != directory.resolve()
        ):
            raise ProtocolError("unsafe output directory")
        os.link(assembler._file, target)
        return {
            "status": "verified",
            "path": str(target),
            "sha256": sha.hexdigest(),
            "md5": md5.hexdigest().upper(),
            "protocol_version": meta.get("version", 1),
        }

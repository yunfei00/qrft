"""Recover from durable SQLite packets using bounded file reads and atomic publication."""

import os
import sqlite3
import tempfile
from pathlib import Path

from qrft.core.missing import export_missing
from qrft.core.protocol import ProtocolError, decode_frame, encode_finish
from qrft.core.reassemble import FileAssembler


def recover(db: sqlite3.Connection, task_id: int, directory: Path) -> dict:
    manifest = db.execute(
        "SELECT start_frame FROM task_manifests WHERE task_id=?", (task_id,)
    ).fetchone()
    if manifest is None:
        raise ProtocolError("START manifest required")
    directory.mkdir(parents=True, exist_ok=True)
    # A crash leaves SQLite intact; a fresh attempt reconstructs the staging file.
    with tempfile.TemporaryDirectory(dir=directory) as staging:
        assembler = FileAssembler(Path(staging))
        assembler.accept(decode_frame(bytes(manifest["start_frame"])))
        for row in db.execute("SELECT frame FROM packets WHERE task_id=?", (task_id,)):
            assembler.accept(decode_frame(bytes(row["frame"])))
        if db.execute("SELECT 1 FROM task_finishes WHERE task_id=?", (task_id,)).fetchone():
            assembler.accept(decode_frame(encode_finish()))
        restored = assembler.finalize()
        export_missing(directory, assembler.manifest["total_packets"], assembler.received)
        if restored is None:
            return {"status": "incomplete"}
        files = directory / "files"
        files.mkdir(exist_ok=True)
        target = files / restored.name
        os.link(restored, target)
        return {"status": "verified", "path": str(target), "sha256": assembler.manifest["sha256"]}

"""从去重后的 v2 数据包恢复文件，并验证文件 MD5。"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .missing import stream_missing
from .protocol import Frame, ProtocolError
from .validation import validate_data, validate_manifest


class PacketIds:
    """Disk-backed receipt index with a fixed-size SQLite cache."""

    def __init__(self):
        # Objects can be finalized by GC in another thread; application access stays serial.
        self.db = sqlite3.connect("", check_same_thread=False)
        self.db.execute("PRAGMA cache_size=-2048")
        self.db.execute("CREATE TABLE received(id INTEGER PRIMARY KEY)")

    def __contains__(self, packet_id):
        return (
            self.db.execute("SELECT 1 FROM received WHERE id=?", (packet_id,)).fetchone()
            is not None
        )

    def add(self, packet_id):
        self.db.execute("INSERT OR IGNORE INTO received VALUES (?)", (packet_id,))

    def __iter__(self):
        return (row[0] for row in self.db.execute("SELECT id FROM received ORDER BY id"))

    def close(self):
        if getattr(self, "db", None) is not None:
            self.db.close()
            self.db = None

    def __del__(self):
        self.close()


class FileAssembler:
    """仅将通过协议 MD5 校验的数据包写入随机访问文件。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest: dict[str, Any] | None = None
        self.received = PacketIds()
        self._file: Path | None = None
        self.finished = False
        self.conflicted = False

    def accept(self, frame: Frame) -> None:
        if frame.version != 2:
            raise ProtocolError("only protocol v2 is supported")
        if frame.kind == "start":
            if self.manifest is not None:
                if frame.metadata != self.manifest:
                    raise ProtocolError("conflicting START metadata")
                return
            meta = frame.metadata
            if meta is None:
                raise ProtocolError("START metadata missing")
            if meta.get("version", 2) != frame.version:
                raise ProtocolError("START metadata version disagrees with wire protocol")
            validate_manifest(meta)
            self.manifest = dict(meta)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".qrft-", suffix=".part", dir=self.directory
            )
            os.close(descriptor)
            self._file = Path(temporary)
            return

        if self.manifest is None or self._file is None:
            raise ProtocolError("START frame required before data")

        if frame.kind == "finish":
            self.finished = True
            return
        if frame.kind != "data":
            raise ProtocolError("unknown frame kind")

        chunk = int(self.manifest["chunk_size"])
        validate_data(self.manifest, frame)
        packet_id = frame.packet_id
        expected = len(frame.payload)
        if packet_id in self.received:
            with self._file.open("rb") as stream:
                stream.seek(packet_id * chunk)
                if stream.read(expected) != frame.payload or (
                    packet_id == self.manifest["total_packets"] - 1
                    and self._file.stat().st_size != packet_id * chunk + expected
                ):
                    self.conflicted = True
                    raise ProtocolError("conflicting duplicate packet")
            return
        with self._file.open("r+b") as stream:
            stream.seek(packet_id * chunk)
            stream.write(frame.payload)
        self.received.add(packet_id)

    def finalize(self) -> Path | None:
        if self.manifest is None or self._file is None:
            raise ProtocolError("no START frame")
        total = int(self.manifest["total_packets"])
        reports = self.directory
        if self.manifest.get("filename") in {"missing.txt", "missing.csv", "missing.json"}:
            reports = self.directory / ".qrft-missing"
        missing = stream_missing(reports, total, self.received)
        if self.conflicted:
            raise ProtocolError("v2 packet conflicts require a new isolated task")
        if missing:
            return None
        md5 = hashlib.md5(usedforsecurity=False)
        with self._file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                md5.update(block)
        if md5.hexdigest().upper() != self.manifest["md5"].upper():
            raise ProtocolError("reassembled file hash mismatch")
        filename = self.manifest.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ProtocolError("unsafe filename")
        if (
            any(ch in filename for ch in '<>:"/\\|?*')
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
        target = self.directory / filename
        if target.exists():
            raise FileExistsError(target)
        os.link(self._file, target)
        self._file.unlink()
        return target

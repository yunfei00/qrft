"""从去重后的 QRFT 数据包恢复文件，并验证 SHA256/MD5。"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from .missing import export_missing
from .protocol import Frame, ProtocolError


class FileAssembler:
    """仅将通过协议 CRC 校验的数据包写入随机访问文件。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest: dict[str, Any] | None = None
        self.received: set[int] = set()
        self._file: Path | None = None
        self.finished = False

    def accept(self, frame: Frame) -> None:
        if frame.kind == "start":
            if self.manifest is not None:
                if frame.metadata != self.manifest:
                    raise ProtocolError("conflicting START metadata")
                return
            meta = frame.metadata
            if meta is None:
                raise ProtocolError("START metadata missing")
            size = meta.get("file_size")
            chunk = meta.get("chunk_size")
            total = meta.get("total_packets")
            if (
                type(size) is not int
                or type(chunk) is not int
                or type(total) is not int
                or size < 0
                or chunk <= 0
                or total != (size + chunk - 1) // chunk
                or total > 88_888_888
            ):
                raise ProtocolError("invalid START manifest sizes")
            if not all(
                isinstance(meta.get(key), str) and len(meta[key]) == length
                for key, length in (("sha256", 64), ("md5", 32))
            ):
                raise ProtocolError("missing manifest hashes")
            self.manifest = dict(meta)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".qrft-", suffix=".part", dir=self.directory
            )
            os.close(descriptor)
            self._file = Path(temporary)
            with self._file.open("wb") as stream:
                stream.truncate(size)
            return

        if self.manifest is None or self._file is None:
            raise ProtocolError("START frame required before data")

        if frame.kind == "finish":
            self.finished = True
            return
        if frame.kind != "data":
            raise ProtocolError("unknown frame kind")

        total = int(self.manifest["total_packets"])
        chunk = int(self.manifest["chunk_size"])
        size = int(self.manifest["file_size"])
        packet_id = frame.packet_id
        if packet_id < 0 or packet_id >= total:
            raise ProtocolError("packet ID outside manifest")
        expected = min(chunk, size - packet_id * chunk)
        if len(frame.payload) != expected:
            raise ProtocolError("incorrect packet length")
        if packet_id in self.received:
            with self._file.open("rb") as stream:
                stream.seek(packet_id * chunk)
                if stream.read(expected) != frame.payload:
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
        missing = export_missing(self.directory, total, self.received)
        if missing or not self.finished:
            return None
        sha = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        with self._file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(block)
                md5.update(block)
        if sha.hexdigest() != self.manifest["sha256"] or md5.hexdigest() != self.manifest["md5"]:
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

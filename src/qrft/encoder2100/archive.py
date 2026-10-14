"""RAM-only deterministic folder archive and versioned logical content digests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import struct
import sys
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_ARCHIVE_MIB = 128
FORMAT = "QRFT2100-FOLDER-1"
PREFIX = b"QRFT2100-FOLDER-CONTENT\x00\x01"
BLOCK = 64 * 1024
RESERVE = 1024 * 1024


def signature(state):
    return (
        state.st_mode & ~0o111 if sys.platform == "win32" else state.st_mode,
        state.st_dev,
        state.st_ino,
        state.st_size,
        state.st_mtime_ns,
        getattr(state, "st_birthtime_ns", state.st_ctime_ns),
        getattr(state, "st_file_attributes", 0),
    )


def reject_link(path, state):
    if stat.S_ISLNK(state.st_mode) or getattr(state, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Symbolic link or Windows reparse point rejected: {path.name}")


@dataclass(frozen=True)
class Entry:
    relative: str
    directory: bool
    state: tuple


def inventory(root: Path, limit: int, cancelled=None):
    entries, visited, charge = [], set(), RESERVE
    pending = [(root, "")]
    while pending:
        directory, relative = pending.pop()
        if cancelled and cancelled():
            raise InterruptedError("Folder archive cancelled")
        state = directory.lstat()
        reject_link(directory, state)
        if not stat.S_ISDIR(state.st_mode):
            raise ValueError("Folder changed while scanning")
        identity = (state.st_dev, state.st_ino)
        if identity in visited:
            raise ValueError("Repeated directory or cycle rejected")
        visited.add(identity)
        entries.append(Entry(relative, True, signature(state)))
        charge += 4096 + 8 * len(relative.encode("utf-8"))
        if charge >= limit:
            raise ValueError("Folder archive memory limit exceeded (entry metadata)")
        with os.scandir(directory) as children:
            for child in children:
                if cancelled and cancelled():
                    raise InterruptedError("Folder archive cancelled")
                name = child.name
                if "\\" in name or name in (".", ".."):
                    raise ValueError("Unsafe ZIP entry name")
                path = f"{relative}/{name}" if relative else name
                # Windows DirEntry.stat omits file IDs; lstat matches subsequent fstat.
                child_state = Path(child.path).lstat()
                reject_link(Path(child.path), child_state)
                if stat.S_ISDIR(child_state.st_mode):
                    # Bound both the pending directory list and finished inventory.
                    charge += 4096 + 8 * len(path.encode("utf-8"))
                    if charge >= limit:
                        raise ValueError("Folder archive memory limit exceeded (directories)")
                    pending.append((Path(child.path), path))
                elif stat.S_ISREG(child_state.st_mode):
                    charge += 4096 + 8 * len(path.encode("utf-8"))
                    if charge >= limit:
                        raise ValueError("Folder archive memory limit exceeded (files)")
                    entries.append(Entry(path, False, signature(child_state)))
                else:
                    raise ValueError("Only regular files and directories can be archived")
    return sorted(entries, key=lambda entry: entry.relative.encode("utf-8")), charge


class BoundedRAM(io.BytesIO):
    def __init__(self, capacity):
        super().__init__()
        self.capacity = capacity

    def write(self, data):
        if self.tell() + len(data) > self.capacity:
            raise ValueError("Folder archive memory limit exceeded (ZIP bytes); no disk fallback")
        return super().write(data)


class MemoryReader(io.RawIOBase):
    """Read-only seekable view: no second full archive copy and independent cursors."""

    def __init__(self, archive):
        self.view = archive.getbuffer().toreadonly()
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        self._checkClosed()
        target = offset + (0 if whence == 0 else self.position if whence == 1 else len(self.view))
        if whence not in (0, 1, 2) or target < 0:
            raise ValueError("Invalid archive seek")
        self.position = target
        return target

    def tell(self):
        return self.position

    def read(self, size=-1):
        self._checkClosed()
        end = len(self.view) if size < 0 else min(len(self.view), self.position + size)
        result = self.view[self.position : end].tobytes()
        self.position = max(self.position, end)
        return result

    def write(self, data):
        raise io.UnsupportedOperation("RAM archive snapshot is read-only")

    def close(self):
        if not self.closed:
            self.view.release()
        super().close()


def checked_open(path: Path, root: Path, expected):
    """Refuse changed/reparse files before reading; Windows denies concurrent writers."""
    before = path.lstat()
    reject_link(path, before)
    if signature(before) != expected or not path.resolve().is_relative_to(root):
        raise ValueError("Folder source changed before reading")
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        handle = create(str(path), 0x80000000, 1, None, 3, 0x08200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError("Cannot read a stable folder snapshot (file busy or inaccessible)")
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        try:
            final = kernel.GetFinalPathNameByHandleW
            final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
            buffer = ctypes.create_unicode_buffer(32768)
            length = final(handle, buffer, len(buffer), 0)
            if not length or length >= len(buffer):
                raise OSError("Cannot verify archive input path")
            actual = buffer.value
            actual = (
                "\\\\" + actual[8:]
                if actual.startswith("\\\\?\\UNC\\")
                else actual.removeprefix("\\\\?\\")
            )
            if not Path(actual).is_relative_to(root):
                raise ValueError("Archive input escaped folder root")
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        stream = os.fdopen(fd, "rb")
    else:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        stream = os.fdopen(fd, "rb")
    try:
        current = os.fstat(stream.fileno())
        reject_link(path, current)
        if not stat.S_ISREG(current.st_mode) or signature(current) != expected:
            raise ValueError("Folder source changed while opening")
        return stream
    except BaseException:
        stream.close()
        raise


def build_archive(path: Path, *, max_mib=DEFAULT_MAX_ARCHIVE_MIB, cancelled=None):
    if not isinstance(max_mib, int) or not 4 <= max_mib <= 4096:
        raise ValueError("max-archive-mib must be 4..4096")
    reject_link(path, path.lstat())
    root = path.resolve(strict=True)
    limit = max_mib * 1024 * 1024
    entries, overhead = inventory(root, limit, cancelled)
    # Reserve metadata twice for the verification inventory, plus BytesIO over-allocation.
    capacity = (limit - 2 * overhead) * 4 // 5
    if capacity <= 0:
        raise ValueError("Folder archive memory limit exceeded (snapshot metadata)")
    archive = BoundedRAM(capacity)
    md5, sha = hashlib.md5(PREFIX), hashlib.sha256(PREFIX)
    file_digests = {}
    try:
        with zipfile.ZipFile(
            archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zipped:
            for entry in entries:
                if cancelled and cancelled():
                    raise InterruptedError("Folder archive cancelled")
                raw_name = entry.relative.encode("utf-8")
                size = 0 if entry.directory else entry.state[3]
                prefix = (
                    (b"D" if entry.directory else b"F")
                    + struct.pack(">Q", len(raw_name))
                    + raw_name
                    + struct.pack(">Q", size)
                )
                md5.update(prefix)
                sha.update(prefix)
                if not entry.relative:
                    continue  # Root has a logical marker but no random outer ZIP directory.
                info = zipfile.ZipInfo(
                    entry.relative + ("/" if entry.directory else ""), (1980, 1, 1, 0, 0, 0)
                )
                info.create_system = 3
                info.create_version = info.extract_version = 20
                info.external_attr = (
                    (stat.S_IFDIR | 0o755) if entry.directory else (stat.S_IFREG | 0o644)
                ) << 16
                if entry.directory:
                    info.external_attr |= 0x10
                info.internal_attr = 0
                info.extra = info.comment = b""
                info.compress_type = zipfile.ZIP_DEFLATED
                info._compresslevel = 6
                content_digest = hashlib.sha256()
                with zipped.open(info, "w", force_zip64=size > zipfile.ZIP64_LIMIT) as target:
                    if not entry.directory:
                        file_path = root / entry.relative
                        with checked_open(file_path, root, entry.state) as source:
                            amount = 0
                            while True:
                                if cancelled and cancelled():
                                    raise InterruptedError("Folder archive cancelled")
                                block = source.read(BLOCK)
                                if not block:
                                    break
                                target.write(block)
                                amount += len(block)
                                md5.update(block)
                                sha.update(block)
                                content_digest.update(block)
                            if (
                                amount != size
                                or signature(os.fstat(source.fileno())) != entry.state
                            ):
                                raise ValueError("Folder source changed during packaging")
                        file_digests[entry.relative] = content_digest.digest()
            comment = {
                "format": FORMAT,
                "folder_content_md5": md5.hexdigest().upper(),
                "folder_content_sha256": sha.hexdigest().upper(),
            }
            zipped.comment = json.dumps(comment, sort_keys=True, separators=(",", ":")).encode(
                "ascii"
            )
        # Re-enumerate, then rehash: detect additions/deletions, renamed/replaced files,
        # and in-place rewrites even if modification timestamps were restored.
        verified, _ = inventory(root, limit, cancelled)
        if verified != entries:
            raise ValueError("Folder source changed during packaging (tree snapshot)")
        for entry in entries:
            if not entry.directory:
                digest = hashlib.sha256()
                with checked_open(root / entry.relative, root, entry.state) as source:
                    while True:
                        if cancelled and cancelled():
                            raise InterruptedError("Folder archive cancelled")
                        block = source.read(BLOCK)
                        if not block:
                            break
                        digest.update(block)
                    if signature(os.fstat(source.fileno())) != entry.state:
                        raise ValueError("Folder source changed during verification")
                if digest.digest() != file_digests[entry.relative]:
                    raise ValueError("Folder content changed during packaging")
        if inventory(root, limit, cancelled)[0] != entries:
            raise ValueError("Folder source changed before snapshot completion")
        with archive.getbuffer() as view:
            details = {
                **comment,
                "archive_zip_md5": hashlib.md5(view).hexdigest().upper(),
                "archive_zip_sha256": hashlib.sha256(view).hexdigest().upper(),
                "zip_size": len(view),
                "archive_buffer_allocated_bytes": archive.__sizeof__(),
                "original_file_bytes": sum(e.state[3] for e in entries if not e.directory),
                "memory_limit_bytes": limit,
                "memory_budget_bytes": 2 * overhead + (len(view) * 5 + 3) // 4,
                "file_count": len(file_digests),
                "directory_count": sum(e.directory and bool(e.relative) for e in entries),
                "python_version": sys.version.split()[0],
                "zlib_version": zlib.ZLIB_VERSION,
                "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
                "compression_level": 6,
            }
        archive.seek(0)
        return archive, details
    except BaseException:
        archive.close()
        raise

"""Verify the published folder fingerprint by streaming ZIP entries, never extracting."""

import hashlib
import json
import stat
import struct
import zipfile
from pathlib import PurePosixPath

from qrft.encoder2100.archive import FORMAT, PREFIX


def verify_folder(path, max_bytes):
    if not zipfile.is_zipfile(path):
        return {"status": "NOT_APPLICABLE", "auto_extracted": False}
    with zipfile.ZipFile(path) as zipped:
        try:
            comment = json.loads(zipped.comment)
        except (ValueError, UnicodeError):
            return {"status": "NOT_APPLICABLE", "auto_extracted": False}
        if not isinstance(comment, dict) or comment.get("format") != FORMAT:
            return {"status": "NOT_APPLICABLE", "auto_extracted": False}
        entries = {}
        for info in zipped.infolist():
            name = info.filename.rstrip("/")
            mode = info.external_attr >> 16
            if (
                not name
                or "\\" in name
                or name.startswith("/")
                or ":" in name
                or any(p in ("", ".", "..") for p in name.split("/"))
                or stat.S_ISLNK(mode)
                or name in entries
            ):
                raise ValueError("Unsafe or duplicate folder ZIP entry")
            if info.flag_bits & 1:
                raise ValueError("Encrypted folder ZIP is unsupported")
            entries[name] = info
        for name in entries:
            for parent in PurePosixPath(name).parents:
                if str(parent) != "." and (
                    str(parent) not in entries or not entries[str(parent)].is_dir()
                ):
                    raise ValueError("Folder ZIP omits directory structure")
        md5, sha = hashlib.md5(PREFIX), hashlib.sha256(PREFIX)
        total = 0
        for name in ["", *sorted(entries, key=lambda n: n.encode("utf-8"))]:
            info = entries.get(name)
            directory = info is None or info.is_dir()
            size = 0 if directory else info.file_size
            total += size
            if total > max_bytes:
                raise ValueError("Folder verification uncompressed byte budget exceeded")
            encoded = name.encode("utf-8")
            header = (
                (b"D" if directory else b"F")
                + struct.pack(">Q", len(encoded))
                + encoded
                + struct.pack(">Q", size)
            )
            md5.update(header)
            sha.update(header)
            if info is not None:
                with zipped.open(info) as stream:
                    read = 0
                    while block := stream.read(65536):
                        if directory:
                            raise ValueError("Directory entry has payload")
                        read += len(block)
                        if read > size:
                            raise ValueError("ZIP length mismatch")
                        md5.update(block)
                        sha.update(block)
                    if read != size:
                        raise ValueError("ZIP entry size mismatch")
        actual_md5, actual_sha = md5.hexdigest().upper(), sha.hexdigest().upper()
        if actual_md5 != comment.get("folder_content_md5") or actual_sha != comment.get(
            "folder_content_sha256"
        ):
            raise ValueError("Folder content fingerprint mismatch")
        return {
            "status": "PASS",
            "folder_content_md5": actual_md5,
            "folder_content_sha256": actual_sha,
            "uncompressed_bytes": total,
            "entries": len(entries),
            "auto_extracted": False,
        }

"""A stable file or deterministic RAM ZIP, encoded with the shared V2 protocol."""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path

from qrft.core.manifest import inspect_file, selected_ranges
from qrft.core.protocol import (
    CHUNK_SIZE,
    START_ID,
    encode_data_v2,
    encode_finish_v2,
    encode_start_v2,
    validate_chunk_size,
)
from qrft.encoder_cli.archive import (
    DEFAULT_MAX_SOURCE_GIB,
    MemoryReader,
    build_archive,
    reject_link,
    source_limit_bytes,
)


def check_cancel(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError("操作已取消，保留本次已生成文件")


class Source:
    """Keep folder ZIP bytes only in RAM; files are read one block at a time."""

    def __init__(
        self,
        path: Path,
        cancelled=None,
        *,
        chunk_size=None,
        max_source_gib=DEFAULT_MAX_SOURCE_GIB,
        expected_archive_md5=None,
    ):
        chunk_size = validate_chunk_size(CHUNK_SIZE if chunk_size is None else chunk_size)
        limit = source_limit_bytes(max_source_gib)
        self.path = Path(path)
        self.cancelled = cancelled
        self._archive = None
        self.archive_details = None
        self.expected_archive_md5 = expected_archive_md5
        check_cancel(cancelled)
        reject_link(self.path, self.path.lstat())
        if self.path.is_dir():
            self._archive, self.archive_details = build_archive(
                self.path, max_source_gib=max_source_gib, cancelled=cancelled
            )
            details = self.archive_details
            size = details["zip_size"]
            self.actual_size = size
            self.metadata = {
                "version": 2,
                "filename": (self.path.resolve().name or "folder") + ".zip",
                "file_size": None,
                "chunk_size": chunk_size,
                "total_packets": (size + chunk_size - 1) // chunk_size,
                "md5": details["archive_zip_md5"],
            }
            if expected_archive_md5 is not None and (
                re.fullmatch(r"[0-9A-Fa-f]{32}", expected_archive_md5) is None
                or expected_archive_md5.upper() != self.metadata["md5"]
            ):
                self.close()
                raise ValueError("Archive ZIP MD5 mismatch; retransmission refused")
        else:
            if expected_archive_md5 is not None:
                raise ValueError("expected-archive-md5 is only valid for folder inputs")
            if not self.path.is_file():
                raise ValueError("输入必须为普通文件或文件夹")
            self.signature = self._signature()
            self.actual_size = self.signature[0]
            if self.actual_size > limit:
                raise ValueError(f"Source file size limit exceeded (maximum {limit} bytes)")
            self.metadata = inspect_file(self.path, chunk_size, cancelled=cancelled)
            self.check()
        if self.metadata["total_packets"] > START_ID:
            self.close()
            raise ValueError("文件超出 DATA 编号上限")

    def _signature(self):
        state = self.path.stat()
        return state.st_size, state.st_mtime_ns, state.st_ino

    def check(self):
        if self._archive is not None:
            if self._archive.closed:
                raise ValueError("Archive source is closed")
        elif self._signature() != self.signature:
            raise ValueError("源文件在编码期间改变；请保留原文件重新编码")

    def open_stream(self):
        return MemoryReader(self._archive) if self._archive is not None else self.path.open("rb")

    def describe(self):
        return {
            **self.metadata,
            **(self.archive_details or {}),
            "file_size": self.actual_size,
            "input_kind": "folder" if self._archive is not None else "file",
        }

    def select(self, *, start_id=0, end_id=None, retransmit=None):
        ranges = list(
            selected_ranges(
                self.metadata["total_packets"],
                start_id=start_id,
                end_id=end_id,
                retransmit=retransmit,
                cancelled=self.cancelled,
            )
        )
        if self._archive is not None and self.expected_archive_md5 is None:
            full = ranges == [(0, self.metadata["total_packets"] - 1)]
            if not full or retransmit is not None or start_id != 0 or end_id is not None:
                raise ValueError("Folder partial selection requires original Archive ZIP MD5")
        return ranges

    def check_output(self, output):
        if self._archive is not None and Path(output).resolve().is_relative_to(self.path.resolve()):
            raise ValueError("Output must be outside the input folder")

    def frames(self, ranges=None, *, repeat_controls=True):
        if ranges is None:
            ranges = self.select()
        else:
            ranges = list(ranges)
            total = self.metadata["total_packets"]
            if any(not 0 <= first <= last < total for first, last in ranges):
                raise ValueError("DATA 范围越界")
            if (
                self._archive is not None
                and self.expected_archive_md5 is None
                and ranges != [(0, total - 1)]
            ):
                raise ValueError("Folder partial selection requires original Archive ZIP MD5")
        check_cancel(self.cancelled)
        self.check()
        chunk_size = self.metadata["chunk_size"]
        start, finish = encode_start_v2(self.metadata), encode_finish_v2()
        for _ in range(20 if repeat_controls else 1):
            check_cancel(self.cancelled)
            yield "START", start
        with self.open_stream() as stream:
            for first, last in ranges:
                stream.seek(first * chunk_size)
                for packet_id in range(first, last + 1):
                    check_cancel(self.cancelled)
                    self.check()
                    expected = min(chunk_size, self.actual_size - packet_id * chunk_size)
                    data = stream.read(expected)
                    if len(data) != expected:
                        raise ValueError("源文件读取不完整")
                    yield f"{packet_id:08d}", encode_data_v2(packet_id, data)
        self.check()
        for _ in range(20 if repeat_controls else 1):
            check_cancel(self.cancelled)
            yield "FINISH", finish

    def close(self):
        if self._archive is not None:
            self._archive.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@contextmanager
def open_source(source, *, cancelled=None, **options):
    """Reuse an inspected CLI source, or own and close a source opened by a helper."""
    if isinstance(source, Source):
        chunk_size = options.get("chunk_size")
        if chunk_size is not None and chunk_size != source.metadata["chunk_size"]:
            raise ValueError("chunk-size does not match the inspected source")
        yield source
    else:
        with Source(source, cancelled=cancelled, **options) as prepared:
            yield prepared

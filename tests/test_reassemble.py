"""文件重组：乱序、重复、缺包及内容一致性。"""

from pathlib import Path

import pytest

from qrft.core.manifest import inspect_file
from qrft.core.protocol import (
    ProtocolError,
    decode_frame,
    encode_data,
    encode_finish,
    encode_start,
)
from qrft.core.reassemble import FileAssembler


def test_out_of_order_duplicate_and_restore(tmp_path: Path) -> None:
    source = tmp_path / "原始.bin"
    payload = bytes(range(256)) + b"\x00\xff"
    source.write_bytes(payload)
    manifest = inspect_file(source, 100)
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(manifest)))
    for index in (2, 0, 0, 1):
        part = payload[index * 100 : (index + 1) * 100]
        assembler.accept(decode_frame(encode_data(index, part)))
    assembler.accept(decode_frame(encode_finish()))
    result = assembler.finalize()
    assert result is not None
    assert result.read_bytes() == payload
    assert (tmp_path / "received" / "missing.txt").read_text() == ""


def test_missing_packets_export(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdefghij")
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(inspect_file(source, 5))))
    assembler.accept(decode_frame(encode_data(0, b"abcde")))
    assembler.accept(decode_frame(encode_finish()))
    assert assembler.finalize() is None
    assert (tmp_path / "received" / "missing.txt").read_text() == "00000001\n"


def test_reject_conflicting_duplicate(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abc")
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(inspect_file(source, 3))))
    assembler.accept(decode_frame(encode_data(0, b"abc")))
    with pytest.raises(ProtocolError, match="conflicting duplicate"):
        assembler.accept(decode_frame(encode_data(0, b"xyz")))


def test_reject_invalid_length(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcd")
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(inspect_file(source, 3))))
    with pytest.raises(ProtocolError, match="incorrect packet length"):
        assembler.accept(decode_frame(encode_data(0, b"ab")))


def test_finish_not_required_and_shorter_tail_conflict(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdef")
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(inspect_file(source, 6))))
    assembler.accept(decode_frame(encode_data(0, b"abcdef")))
    with pytest.raises(ProtocolError, match="conflicting"):
        assembler.accept(decode_frame(encode_data(0, b"abc")))
    with pytest.raises(ProtocolError, match="conflicts"):
        assembler.finalize()
    complete = FileAssembler(tmp_path / "complete")
    complete.accept(decode_frame(encode_start(inspect_file(source, 6))))
    complete.accept(decode_frame(encode_data(0, b"abcdef")))
    assert complete.finalize().read_bytes() == b"abcdef"


def test_file_md5_mismatch_blocks_publication(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdef")
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(inspect_file(source, 3))))
    assembler.accept(decode_frame(encode_data(0, b"abc")))
    assembler.accept(decode_frame(encode_data(1, b"xyz")))
    with pytest.raises(ProtocolError, match="hash mismatch"):
        assembler.finalize()
    assert not (tmp_path / "received" / source.name).exists()


@pytest.mark.parametrize(
    "filename", ["../escape", r"..\escape", "CON.bin", "file:stream", "trail."]
)
def test_windows_unsafe_filename(tmp_path, filename):
    source = tmp_path / "safe.bin"
    source.write_bytes(b"")
    meta = inspect_file(source, 3)
    meta["filename"] = filename
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(meta)))
    assembler.accept(decode_frame(encode_finish()))
    with pytest.raises(ProtocolError, match="unsafe filename"):
        assembler.finalize()


def test_scratch_and_target_never_overwrite_existing_files(tmp_path):
    source = tmp_path / "received.part"
    source.write_bytes(b"abc")
    directory = tmp_path / "received"
    directory.mkdir()
    target = directory / "received.part"
    target.write_bytes(b"user data")
    assembler = FileAssembler(directory)
    assembler.accept(decode_frame(encode_start(inspect_file(source, 3))))
    assembler.accept(decode_frame(encode_data(0, b"abc")))
    assembler.accept(decode_frame(encode_finish()))
    with pytest.raises(FileExistsError):
        assembler.finalize()
    assert target.read_bytes() == b"user data"

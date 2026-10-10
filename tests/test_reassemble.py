"""文件重组：乱序、重复、缺包及内容一致性。"""

from pathlib import Path

import pytest

from qrft.core.manifest import inspect_file
from qrft.core.protocol import ProtocolError, decode_frame, encode_data, encode_finish, encode_start
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
    source.write_bytes(b"abc")
    assembler = FileAssembler(tmp_path / "received")
    assembler.accept(decode_frame(encode_start(inspect_file(source, 3))))
    with pytest.raises(ProtocolError, match="incorrect packet length"):
        assembler.accept(decode_frame(encode_data(0, b"ab")))

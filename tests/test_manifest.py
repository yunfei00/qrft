import hashlib
from pathlib import Path

import pytest

from qrft.core.manifest import inspect_file, packet_bytes, parse_packet_list
from qrft.core.protocol import ProtocolError


def test_manifest_and_chunks(tmp_path: Path) -> None:
    file = tmp_path / "文件.bin"
    file.write_bytes(b"\x00\xffabc")
    meta = inspect_file(file, 2)
    assert meta["total_packets"] == 3
    assert meta["sha256"] == hashlib.sha256(b"\x00\xffabc").hexdigest()
    assert packet_bytes(file, 2, 0) == b"\x00\xff"
    assert packet_bytes(file, 2, 2) == b"c"


def test_empty_file(tmp_path: Path) -> None:
    file = tmp_path / "empty"
    file.touch()
    assert inspect_file(file, 512)["total_packets"] == 0


def test_packet_list() -> None:
    assert parse_packet_list("00000003\n1-2\n# comment\n2\n", 10) == [1, 2, 3]
    with pytest.raises(ProtocolError):
        parse_packet_list("1-11", 10)
    with pytest.raises(ProtocolError):
        parse_packet_list("abc", 10)

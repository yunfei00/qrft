"""实时播放帧序列的纯逻辑测试，不依赖显示器。"""

from pathlib import Path

import pytest

from qrft.core.protocol import decode_frame
from qrft.encoder_cli.playback import iter_encoded_frames


def test_playback_sequence(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    frames = list(iter_encoded_frames(source, chunk_size=2))
    assert [name for name, _ in frames] == [
        "START",
        "00000000",
        "00000001",
        "00000002",
        "FINISH",
    ]
    assert b"".join(decode_frame(raw).payload for _, raw in frames) == b"abcdef"


def test_retransmit_only_selected(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    missing = tmp_path / "missing.txt"
    missing.write_text("00000002\n00000000\n", encoding="ascii")
    frames = list(iter_encoded_frames(source, chunk_size=2, retransmit=missing))
    assert [name for name, _ in frames] == ["START", "00000000", "00000002", "FINISH"]


def test_packet_id_bounds(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    frames = list(iter_encoded_frames(source, chunk_size=2, start_id=1, end_id=1))
    assert [name for name, _ in frames] == ["START", "00000001", "FINISH"]


def test_retransmit_intersects_bounds(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    missing = tmp_path / "missing.txt"
    missing.write_text("0\n1\n2\n", encoding="ascii")
    frames = list(
        iter_encoded_frames(source, chunk_size=2, retransmit=missing, start_id=1, end_id=2)
    )
    assert [name for name, _ in frames] == ["START", "00000001", "00000002", "FINISH"]


def test_invalid_packet_bounds(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    with pytest.raises(ValueError):
        list(iter_encoded_frames(source, chunk_size=2, start_id=-1))
    with pytest.raises(ValueError):
        list(iter_encoded_frames(source, chunk_size=2, start_id=2, end_id=1))
    with pytest.raises(ValueError):
        list(iter_encoded_frames(source, chunk_size=2, end_id=3))


def test_empty_file_has_control_frames(tmp_path: Path) -> None:
    source = tmp_path / "empty.bin"
    source.write_bytes(b"")
    frames = list(iter_encoded_frames(source))
    assert [name for name, _ in frames] == ["START", "FINISH"]

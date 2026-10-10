"""实时播放帧序列的纯逻辑测试，不依赖显示器。"""

from pathlib import Path

from qrft.core.protocol import decode_frame
from qrft.encoder_cli.playback import iter_encoded_frames


def test_playback_sequence(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    frames = list(iter_encoded_frames(source, chunk_size=2))
    assert [name for name, _ in frames] == [
        "START", "00000000", "00000001", "00000002", "FINISH"
    ]
    assert b"".join(decode_frame(raw).payload for _, raw in frames) == b"abcdef"


def test_retransmit_only_selected(tmp_path: Path) -> None:
    source = tmp_path / "data.bin"
    source.write_bytes(b"abcdef")
    missing = tmp_path / "missing.txt"
    missing.write_text("00000002\n00000000\n", encoding="ascii")
    frames = list(iter_encoded_frames(source, chunk_size=2, retransmit=missing))
    assert [name for name, _ in frames] == ["START", "00000000", "00000002", "FINISH"]

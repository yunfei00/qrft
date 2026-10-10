"""真实 AVI 视频文件：二维码编码、视频解码、原文件哈希恢复。"""

from pathlib import Path

import pytest

from qrft.decoder.main import restore_video
from qrft.encoder_cli.video_export import export_video


@pytest.mark.parametrize(
    "filename,payload",
    [
        ("空文件.bin", b""),
        ("文本.txt", "二维码传输".encode()),
        ("文档.pdf", b"%PDF-1.7\x00\xffbinary"),
        ("压缩.zip", b"PK\x03\x04\x00\xff"),
        ("程序.exe", b"MZ\x00\xffbinary"),
        ("payload.bin", bytes(range(256)) + b"\x00\xff"),
    ],
)
def test_real_video_roundtrip(tmp_path: Path, filename, payload) -> None:
    pytest.importorskip("cv2")
    pytest.importorskip("zxingcpp")
    source = tmp_path / filename
    source.write_bytes(payload)
    video = export_video(source, tmp_path / "recording.avi", chunk_size=64, fps=5, repeats=5)
    restored = restore_video(video, tmp_path / "recovered", sample_fps=5)
    assert restored is not None
    assert restored.read_bytes() == payload

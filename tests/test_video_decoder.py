"""视频帧采样与恢复流程的确定性测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from qrft.core.manifest import inspect_file
from qrft.core.protocol import decode_frame, encode_data, encode_finish, encode_start
from qrft.decoder.main import restore_video
from qrft.decoder.video import iter_video_frames


def test_video_recovery_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "原始.bin"
    source.write_bytes(bytes(range(200)))
    meta = inspect_file(source, 100)
    frames = [
        decode_frame(encode_start(meta)),
        decode_frame(encode_data(1, bytes(range(100, 200)))),
        decode_frame(encode_data(0, bytes(range(100)))),
        decode_frame(encode_finish()),
    ]
    with patch("qrft.decoder.main.iter_video_frames", return_value=iter(frames)):
        result = restore_video(tmp_path / "placeholder.mp4", tmp_path / "out")
    assert result is not None
    assert result.read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_fps": 0},
        {"start_seconds": -1},
        {"start_seconds": 2, "end_seconds": 1},
    ],
)
def test_invalid_video_sampling_args(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        list(iter_video_frames(Path("unused.mp4"), **kwargs))

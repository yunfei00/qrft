"""按时间采样录屏视频，直接解码 QRFT 原始二进制帧。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from qrft.core.protocol import Frame, ProtocolError, decode_frame


def iter_video_frames(
    path: Path,
    *,
    sample_fps: float = 10.0,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> Iterator[Frame]:
    """顺序扫描选定时间范围；损坏/非 QR 画面忽略，合法帧按出现顺序返回。"""
    if sample_fps <= 0 or start_seconds < 0:
        raise ValueError("sample_fps must be positive and start_seconds nonnegative")
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("end_seconds must exceed start_seconds")

    import cv2
    import zxingcpp

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise OSError(f"cannot open video: {path}")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise OSError("video FPS unavailable")
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        start_index = max(0, int(start_seconds * fps))
        end_index = total_frames if end_seconds is None else min(total_frames, int(end_seconds * fps))
        step = max(1, round(fps / sample_fps))
        for index in range(start_index, end_index, step):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, image = capture.read()
            if not ok:
                continue
            for barcode in zxingcpp.read_barcodes(image):
                try:
                    yield decode_frame(bytes(barcode.bytes))
                except ProtocolError:
                    continue
    finally:
        capture.release()

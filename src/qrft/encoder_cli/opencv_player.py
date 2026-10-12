"""OpenCV v2 player; retains the exact 50%-scaled QR and its quiet zone."""

import time
from pathlib import Path

from qrft.encoder_cli.playback import iter_encoded_frames
from qrft.encoder_cli.prefetch import prefetch_png


def play_opencv(
    source: Path,
    *,
    protocol_version=2,
    chunk_size=None,
    interval_ms=None,
    initial_delay_ms=3000,
    retransmit=None,
    start_id=0,
    end_id=None,
):
    if protocol_version != 2:
        raise ValueError("OpenCV path currently requires v2")
    interval_ms = 50 if interval_ms is None else interval_ms
    if interval_ms < 1 or initial_delay_ms < 0:
        raise ValueError("invalid playback timing")
    import sys

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    import cv2
    import numpy as np

    frames = prefetch_png(
        iter_encoded_frames(
            source,
            protocol_version=2,
            chunk_size=chunk_size,
            retransmit=retransmit,
            start_id=start_id,
            end_id=end_id,
        ),
        protocol_version=2,
        workers=2,
        capacity=4,
    )
    name = "QRFT v2 - Space pause / Esc stop"
    opened = False
    try:
        for (label, _), png in frames:
            image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise OSError("cannot load QR image")
            # START can be smaller than DATA: a constant canvas keeps the recording
            # rectangle stable without rescaling or clipping any QR pixels.
            h, w = image.shape[:2]
            if max(h, w) > 926:
                raise ValueError("QR exceeds v2 canvas")
            canvas = np.full((926, 926, 3), 255, dtype=np.uint8)
            y, x = (926 - h) // 2, (926 - w) // 2
            canvas[y : y + h, x : x + w] = image
            import sys

            if sys.platform == "win32":
                import ctypes

                width = ctypes.windll.user32.GetSystemMetrics(0)
                height = ctypes.windll.user32.GetSystemMetrics(1)
                if canvas.shape[1] > width - 40 or canvas.shape[0] > height - 80:
                    raise ValueError(
                        "显示器空间不足，无法完整显示50%二维码；请使用更大屏幕，不更改协议参数"
                    )
            if not opened:
                cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
                opened = True
                # Blank delay: do not accidentally hold the first START beyond its schedule.
                cv2.imshow(name, np.full_like(canvas, 255))
                deadline = time.monotonic() + initial_delay_ms / 1000
                while time.monotonic() < deadline:
                    if cv2.waitKey(20) & 0xFF == 27:
                        return 130
            cv2.imshow(name, canvas)
            delay = 50 if label in ("START", "FINISH") else interval_ms
            key = cv2.waitKey(delay) & 0xFF
            if key == 27 or cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) < 1:
                return 130
            if key == 32:
                while True:
                    key = cv2.waitKey(30) & 0xFF
                    if key == 27:
                        return 130
                    if key == 32:
                        break
        return 0
    finally:
        frames.close()
        if opened:
            cv2.destroyWindow(name)

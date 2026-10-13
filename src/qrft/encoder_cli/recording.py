"""Fixed recording geometry and key edge handling shared by encoder players."""

QR_SIDE = 926
PADDING = 10
HEADER = 24
FOOTER = 48


class KeyLatch:
    """Debounce key-repeat on backends without key-release events."""

    def __init__(self):
        self.last_space = float("-inf")

    def press(self, key, now):
        if key != 32:
            return False
        fresh = now - self.last_space > 0.3
        self.last_space = now
        return fresh


def recording_canvas(image, label, state):
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    if max(h, w) > QR_SIDE:
        raise ValueError("二维码超过固定录屏区域；请检查文件名/参数，不要改变 v2 分块")
    canvas = np.full((QR_SIDE + HEADER + FOOTER, QR_SIDE + PADDING * 2, 3), 245, np.uint8)
    canvas[HEADER : HEADER + QR_SIDE, PADDING : PADDING + QR_SIDE] = 255
    x = PADDING + (QR_SIDE - w) // 2
    y = HEADER + (QR_SIDE - h) // 2
    canvas[y : y + h, x : x + w] = image
    cv2.putText(
        canvas,
        "QRFT | RECORD THE WHITE SQUARE",
        (10, 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (50, 50, 50),
        1,
    )
    cv2.putText(
        canvas,
        f"{state} | {label}",
        (10, HEADER + QR_SIDE + 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (50, 50, 50),
        1,
    )
    cv2.putText(
        canvas,
        "Space: start/pause/resume | Esc: stop",
        (10, canvas.shape[0] - 9),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (50, 50, 50),
        1,
    )
    return canvas

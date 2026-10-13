"""以 QR Byte 模式生成图片，避免将二进制帧转换成文本。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def qr_png(frame: bytes, *, box_size: int = 8, border: int = 4, correction: str = "M") -> bytes:
    """生成 PNG 字节；容量不足时抛出 ValueError，绝不截断帧。"""
    if not isinstance(frame, bytes):
        raise TypeError("QR frame must be bytes")
    if box_size < 1 or border < 4:
        raise ValueError("box_size must be positive and border >= 4")
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
    from qrcode.exceptions import DataOverflowError
    from qrcode.util import MODE_8BIT_BYTE, QRData

    levels = {
        "L": ERROR_CORRECT_L,
        "M": ERROR_CORRECT_M,
        "Q": ERROR_CORRECT_Q,
        "H": ERROR_CORRECT_H,
    }
    if correction not in levels:
        raise ValueError("correction must be L, M, Q or H")
    qr = qrcode.QRCode(
        version=None,
        error_correction=levels[correction],
        box_size=box_size,
        border=border,
    )
    qr.add_data(QRData(frame, mode=MODE_8BIT_BYTE))
    try:
        qr.make(fit=True)
    except DataOverflowError as exc:
        raise ValueError("QR frame exceeds symbol capacity") from exc
    stream = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(stream, format="PNG")
    return stream.getvalue()


def save_qr_png(frame: bytes, destination: Path) -> None:
    destination.write_bytes(qr_png(frame))


def v2_image(frame: bytes):
    """Exact v2 parameters, automatic mode, PIL -> BGR -> 50% nearest neighbor."""
    from .protocol_v2 import decode_v2

    decode_v2(frame)
    import cv2
    import numpy as np
    import qrcode
    from qrcode.exceptions import DataOverflowError

    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4
    )
    qr.add_data(frame.decode("ascii"))
    try:
        qr.make(fit=True)
    except (DataOverflowError, ValueError) as exc:
        raise ValueError(
            "v2 QR capacity exceeded; shorten filename, do not change 1400-byte blocks"
        ) from exc
    pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    bgr = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    return cv2.resize(bgr, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)


def render_png(frame: bytes, *, protocol_version=1, **options) -> bytes:
    """Same renderer for PNG export and Qt playback."""
    if protocol_version == 1:
        return qr_png(frame, **options)
    if any(k not in {"correction", "box_size", "border"} for k in options):
        raise ValueError("unsupported v2 QR option")
    if any(
        options.get(k, value) != value
        for k, value in (("correction", "L"), ("box_size", 10), ("border", 4))
    ):
        raise ValueError("v2 requires correction L, box size 10, border 4")
    import cv2

    ok, png = cv2.imencode(".png", v2_image(frame))
    if not ok:
        raise OSError("cannot encode v2 QR PNG")
    return png.tobytes()

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

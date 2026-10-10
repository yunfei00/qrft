"""从二维码图片读取原始字节并校验 QRFT 协议。"""

from __future__ import annotations

from io import BytesIO

from qrft.core.protocol import Frame, ProtocolError, decode_frame


def decode_qr_png(png: bytes) -> Frame:
    """解码 PNG，严格使用 ZXing 返回的原始字节，不使用文本字段。"""
    if not isinstance(png, bytes):
        raise TypeError("PNG input must be bytes")

    import zxingcpp
    from PIL import Image

    with Image.open(BytesIO(png)) as image:
        result = zxingcpp.read_barcode(image.convert("RGB"))
    if result is None:
        raise ProtocolError("QR code not detected")
    raw = result.bytes
    if not isinstance(raw, bytes):
        raw = bytes(raw)
    return decode_frame(raw)

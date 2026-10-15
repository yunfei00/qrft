"""Exact 40-L alphanumeric QR raster; no desktop or OpenCV initialization."""

import io

from .protocol import HEX


def qr_code(text: str):
    import qrcode
    from qrcode.util import MODE_ALPHA_NUM, QRData

    if not text or not HEX.fullmatch(text):
        raise ValueError("二维码内容必须全部为大写 HEX")
    qr = qrcode.QRCode(
        version=40, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=5, border=4
    )
    qr.add_data(QRData(text, mode=MODE_ALPHA_NUM), optimize=0)
    try:
        from .codewords import create_codewords

        qr.data_cache = create_codewords(qr)
        qr.make(fit=False)
    except qrcode.exceptions.DataOverflowError as exc:
        raise ValueError("QRFT2100 Version 40-L 容量溢出；不截断、不改变分块") from exc
    return qr


def image(text: str):
    return qr_code(text).make_image(fill_color="black", back_color="white").convert("RGB")


def png(text: str) -> bytes:
    stream = io.BytesIO()
    image(text).save(stream, format="PNG")
    return stream.getvalue()

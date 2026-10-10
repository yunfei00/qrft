"""测试 Byte 模式图片生成；无需连接相机或录屏。"""

from io import BytesIO

import pytest

from qrft.core.protocol import encode_data
from qrft.core.qr_image import qr_png


def test_qr_png_binary_payload() -> None:
    pytest.importorskip("qrcode")
    from PIL import Image

    raw = encode_data(7, bytes(range(256)))
    png = qr_png(raw)
    image = Image.open(BytesIO(png))
    assert image.format == "PNG"
    assert image.width == image.height
    assert image.width > 100


def test_qr_png_requires_binary() -> None:
    with pytest.raises(TypeError):
        qr_png("hello")


def test_qr_png_rejects_invalid_border() -> None:
    with pytest.raises(ValueError):
        qr_png(b"hello", border=1)

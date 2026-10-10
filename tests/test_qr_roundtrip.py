"""真正的二维码图像编码-识别-二进制协议往返测试。"""

from io import BytesIO

import pytest

from qrft.core.protocol import decode_frame, encode_data, encode_finish, encode_start
from qrft.core.qr_decode import decode_qr_png
from qrft.core.qr_image import qr_png


@pytest.mark.parametrize(
    ("packet_id", "payload"),
    [
        (0, b""),
        (1, b"\x00\xff\xfe\x80\x00"),
        (2, bytes(range(256))),
        (3, b"\x00" * 64 + b"\xff" * 64),
    ],
)
def test_data_png_roundtrip(packet_id: int, payload: bytes) -> None:
    pytest.importorskip("zxingcpp")
    frame = encode_data(packet_id, payload)
    result = decode_qr_png(qr_png(frame))
    assert result == decode_frame(frame)
    assert result.payload == payload


def test_start_and_finish_png_roundtrip() -> None:
    pytest.importorskip("zxingcpp")
    metadata = {"filename": "测试-😀.bin", "size": 5, "sha256": "abc"}
    start = encode_start(metadata)
    finish = encode_finish()
    assert decode_qr_png(qr_png(start)) == decode_frame(start)
    assert decode_qr_png(qr_png(finish)) == decode_frame(finish)


def test_corrupt_png_is_rejected() -> None:
    pytest.importorskip("zxingcpp")
    from PIL import Image

    image = Image.new("RGB", (100, 100), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    with pytest.raises(Exception, match="QR code not detected"):
        decode_qr_png(output.getvalue())

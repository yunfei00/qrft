"""The production v2 renderer can scan full 2100-byte and maximum-size blocks."""

import random
from io import BytesIO

import pytest

from qrft.core.protocol import (
    MAX_CHUNK_SIZE,
    decode_frame,
    encode_data,
    encode_finish,
    encode_start,
)
from qrft.core.qr_image import qr_png, render_png, v2_image


@pytest.mark.parametrize("size", [1400, 2100, MAX_CHUNK_SIZE])
def test_actual_qr_roundtrip_and_parameters(monkeypatch, size):
    import cv2
    import numpy as np
    import qrcode
    import zxingcpp
    from qrcode.util import MODE_ALPHA_NUM, MODE_NUMBER

    original = qrcode.QRCode
    created = []

    def observed(*args, **kwargs):
        assert kwargs == {
            "version": None,
            "error_correction": qrcode.constants.ERROR_CORRECT_L,
            "box_size": 10,
            "border": 4,
        }
        qr = original(*args, **kwargs)
        created.append(qr)
        return qr

    monkeypatch.setattr(qrcode, "QRCode", observed)
    payload = random.Random(size).randbytes(size)
    raw = encode_data(0, payload)
    image = v2_image(raw)
    qr = created[0]
    assert all(d.mode in (MODE_ALPHA_NUM, MODE_NUMBER) for d in qr.data_list)
    assert image.shape[:2] == ((17 + 4 * qr.version + 8) * 5,) * 2
    full = cv2.cvtColor(np.asarray(qr.make_image().convert("RGB")), cv2.COLOR_RGB2BGR)
    assert np.array_equal(
        image, cv2.resize(full, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)
    )
    symbols = zxingcpp.read_barcodes(image)
    assert len(symbols) == 1 and bytes(symbols[0].bytes) == raw
    assert decode_frame(bytes(symbols[0].bytes)).payload == payload


def test_png_output():
    from PIL import Image

    image = Image.open(BytesIO(qr_png(encode_data(7, bytes(range(256))))))
    assert image.format == "PNG"
    assert image.width == image.height


@pytest.mark.parametrize("size", [2100, MAX_CHUNK_SIZE])
def test_dense_digit_runs_fit_maximum_symbol(size):
    import zxingcpp

    payload = (bytes(range(256)) * 9)[:size]
    raw = encode_data(0, payload)
    image = v2_image(raw)
    assert image.shape[:2] == (925, 925)
    symbols = zxingcpp.read_barcodes(image)
    assert len(symbols) == 1
    assert bytes(symbols[0].bytes) == raw


def test_capacity_and_parameter_errors():
    raw = encode_start({"filename": "长" * 4000, "md5": "A" * 32, "total_packets": 1})
    with pytest.raises(ValueError, match="capacity"):
        render_png(raw)
    with pytest.raises(ValueError, match="requires"):
        render_png(encode_finish(), correction="M")
    with pytest.raises(ValueError, match="requires"):
        qr_png(encode_finish(), border=1)
    with pytest.raises(ValueError, match="only protocol v2"):
        render_png(encode_finish(), protocol_version=1)
    with pytest.raises(TypeError):
        qr_png("hello")

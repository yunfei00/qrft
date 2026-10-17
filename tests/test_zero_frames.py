"""Zero-heavy file blocks must survive QR generation, video decoding and recovery."""

import random

import pytest

from qrft.core.protocol import MAX_CHUNK_SIZE, decode_frame, encode_data
from qrft.core.qr_decode import decode_qr_png
from qrft.core.qr_image import render_png
from qrft.decoder.main import restore_video
from qrft.encoder_cli.video_export import export_video


@pytest.mark.parametrize("size", [1, 1400, 2100, MAX_CHUNK_SIZE])
@pytest.mark.parametrize("packet_id", [0, 1, 88_888_887])
def test_all_zero_frame_qr_roundtrip(size, packet_id):
    payload = bytes(size)
    raw = encode_data(packet_id, payload)
    restored = decode_qr_png(render_png(raw))
    assert restored == decode_frame(raw)
    assert restored.packet_id == packet_id and restored.payload == payload


@pytest.mark.parametrize(
    "payload",
    [
        b"prefix" + bytes(2088) + b"suffix",
        bytes(2100 - 16) + random.Random(1).randbytes(16),
        random.Random(2).randbytes(16) + bytes(2100 - 16),
    ],
)
def test_zero_heavy_frame_qr_roundtrip(payload):
    raw = encode_data(7, payload)
    assert decode_qr_png(render_png(raw)).payload == payload


def test_all_zero_file_video_recovery(tmp_path):
    source = tmp_path / "zeros.bin"
    payload = bytes(2100 * 2 + 17)
    source.write_bytes(payload)
    video = export_video(source, tmp_path / "zeros.avi")
    restored = restore_video(video, tmp_path / "restored")
    assert restored is not None and restored.read_bytes() == payload


def test_unrelated_qr_error_is_not_reported_as_capacity(monkeypatch):
    import qrcode

    def broken(*_args, **_kwargs):
        raise ValueError("unrelated QR encoder failure")

    monkeypatch.setattr(qrcode.QRCode, "make", broken)
    with pytest.raises(ValueError, match="^unrelated QR encoder failure$"):
        render_png(encode_data(0, b"data"))


@pytest.mark.parametrize("version", range(1, 41))
@pytest.mark.parametrize("correction", [0, 1, 2, 3])
@pytest.mark.parametrize("payload", [b"HELLO", b"12345", b"\x00\x01\x80\xff\x00"])
def test_fallback_codewords_match_qrcode_for_every_version_and_correction(
    version, correction, payload
):
    from qrcode import util

    from qrft.core._qr_rs import create_codewords

    segments = [util.QRData(payload)]
    assert create_codewords(version, correction, segments) == util.create_data(
        version, correction, segments
    )


def test_zero_and_random_frames_can_be_generated_in_parallel():
    from concurrent.futures import ThreadPoolExecutor

    from qrcode import base

    original_mod = base.Polynomial.__mod__
    payloads = [bytes(2100), random.Random(5).randbytes(2100)] * 3
    frames = [encode_data(index, payload) for index, payload in enumerate(payloads)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        pngs = list(pool.map(render_png, frames))
    assert [decode_qr_png(png).payload for png in pngs] == payloads
    assert base.Polynomial.__mod__ is original_mod

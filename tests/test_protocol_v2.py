"""Real v2 wire bytes, hashing, reserved IDs and QR rendering settings."""

import hashlib
import random

import pytest

from qrft.core.manifest import inspect_file
from qrft.core.protocol import ProtocolError, decode_frame, encode_data, serialize_frame
from qrft.core.protocol_v2 import (
    decode_v2,
    encode_data_v2,
    encode_finish_v2,
    encode_start_v2,
    wrap_v2,
)
from qrft.core.qr_image import render_png, v2_image
from qrft.core.reassemble import FileAssembler
from qrft.encoder_cli.playback import iter_encoded_frames


@pytest.mark.parametrize("filename", ["空.bin", "中文,带,逗号.exe", "data.pdf"])
@pytest.mark.parametrize("payload", [b"", b"\x00\xff\x80", bytes(range(256)) * 6])
def test_start_metadata_and_schedule(tmp_path, filename, payload):
    source = tmp_path / filename
    source.write_bytes(payload)
    frames = list(iter_encoded_frames(source, protocol_version=2))
    total = (len(payload) + 1399) // 1400
    assert len(frames) == 40 + total
    assert [name for name, _ in frames[:20]] == ["START"] * 20
    assert [name for name, _ in frames[-20:]] == ["FINISH"] * 20
    start = decode_frame(frames[0][1])
    assert start.version == 2
    assert start.metadata["filename"] == filename
    assert start.metadata["md5"] == hashlib.md5(payload).hexdigest().upper()
    assert start.metadata["total_packets"] == total
    assert start.metadata["file_size"] is None
    assert frames[0][1][-16:] == b"3838383838383838"
    assert frames[-1][1][-16:] == b"3939393939393939"
    data = [decode_frame(raw) for name, raw in frames if name not in ("START", "FINISH")]
    assert [d.packet_id for d in data] == list(range(total))
    assert b"".join(d.payload for d in data) == payload
    assert all(serialize_frame(decode_frame(raw)) == raw for _, raw in frames)


@pytest.mark.parametrize("length", [1, 255, 1399, 1400])
def test_data_exact_layout(length):
    payload = random.Random(length).randbytes(length)
    raw = encode_data_v2(1, payload)
    assert (
        raw
        == (
            payload.hex().upper() + hashlib.md5(payload).hexdigest().upper() + "3030303030303031"
        ).encode()
    )
    assert len(raw) == length * 2 + 48
    assert decode_v2(raw).payload == payload
    assert decode_frame(encode_data(1, payload)).version == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"A" * 49,
        b"G" * 50,
        encode_data_v2(0, b"x").lower(),
        encode_data_v2(0, b"x")[:-48] + b"0" * 32 + encode_data_v2(0, b"x")[-16:],
        encode_data_v2(0, b"x")[:-16] + b"4141414141414141",
        wrap_v2(b"x", 88888889),
        wrap_v2(b"Finish", 99999999),
        wrap_v2(b"name,notmd5,1", 88888888),
        wrap_v2(b"name," + b"A" * 32 + b",-1", 88888888),
        wrap_v2(b"name," + b"A" * 32 + b",88888889", 88888888),
        wrap_v2(b"\xff," + b"A" * 32 + b",0", 88888888),
    ],
)
def test_invalid_frames(raw):
    with pytest.raises(ProtocolError):
        decode_v2(raw)


def test_empty_and_oversized_data_rejected():
    for payload in (b"", b"x" * 1401):
        with pytest.raises(ProtocolError):
            encode_data_v2(0, payload)
    for packet_id in (-1, 88888888, 99999999, True):
        with pytest.raises(ProtocolError):
            encode_data_v2(packet_id, b"x")
    assert decode_v2(encode_finish_v2()).kind == "finish"


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_actual_1400_byte_qr_and_exact_parameters(monkeypatch, seed):
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
        make = qr.make

        def checked_make(*args, **kwargs):
            assert kwargs == {"fit": True}
            return make(*args, **kwargs)

        qr.make = checked_make
        created.append(qr)
        return qr

    monkeypatch.setattr(qrcode, "QRCode", observed)
    raw = encode_data_v2(0, random.Random(seed).randbytes(1400))
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
    assert decode_frame(bytes(symbols[0].bytes)).payload == random.Random(seed).randbytes(1400)


def test_capacity_error_does_not_change_settings():
    raw = encode_start_v2({"filename": "长" * 4000, "md5": "A" * 32, "total_packets": 1})
    with pytest.raises(ValueError, match="capacity"):
        render_png(raw, protocol_version=2)
    with pytest.raises(ValueError, match="requires"):
        render_png(encode_finish_v2(), protocol_version=2, correction="M")


def test_assembler_out_of_order_duplicates_and_hash_failure(tmp_path):
    source = tmp_path / "safe,中文.bin"
    payload = random.Random(8).randbytes(1405)
    source.write_bytes(payload)
    meta = inspect_file(source, 1400)
    assembler = FileAssembler(tmp_path / "good")
    assembler.accept(decode_frame(encode_start_v2(meta)))
    assembler.accept(decode_frame(encode_start_v2(meta)))
    for packet_id in (1, 0, 1):
        assembler.accept(
            decode_frame(
                encode_data_v2(packet_id, payload[packet_id * 1400 : (packet_id + 1) * 1400])
            )
        )
    assert (
        assembler.finalize().read_bytes() == payload
    )  # FINISH is not a success prerequisite in v2.
    bad = FileAssembler(tmp_path / "bad")
    bad.accept(decode_frame(encode_start_v2(meta)))
    bad.accept(decode_frame(encode_data_v2(0, b"z" * 1400)))
    bad.accept(decode_frame(encode_data_v2(1, payload[1400:])))
    with pytest.raises(ProtocolError, match="hash mismatch"):
        bad.finalize()


def test_shorter_conflicting_tail_is_not_a_duplicate(tmp_path):
    assembler = FileAssembler(tmp_path)
    assembler.accept(
        decode_frame(encode_start_v2({"filename": "x.bin", "md5": "A" * 32, "total_packets": 1}))
    )
    assembler.accept(decode_frame(encode_data_v2(0, b"abcdef")))
    with pytest.raises(ProtocolError, match="conflicting"):
        assembler.accept(decode_frame(encode_data_v2(0, b"abc")))
    with pytest.raises(ProtocolError, match="conflicts"):
        assembler.finalize()

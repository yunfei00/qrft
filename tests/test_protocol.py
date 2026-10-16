"""The single v2 wire format, adjustable blocks and rejected legacy frames."""

import hashlib
import random
import zlib

import pytest

from qrft.core.protocol import (
    CHUNK_SIZE,
    FINISH_ID,
    MAX_CHUNK_SIZE,
    START_ID,
    Frame,
    ProtocolError,
    decode_frame,
    encode_data,
    encode_finish,
    encode_start,
    serialize_frame,
    wrap_v2,
)


@pytest.mark.parametrize("length", [1, 255, 1400, CHUNK_SIZE, MAX_CHUNK_SIZE])
def test_data_exact_layout(length):
    payload = random.Random(length).randbytes(length)
    raw = encode_data(1, payload)
    assert (
        raw
        == (
            payload.hex().upper() + hashlib.md5(payload).hexdigest().upper() + "3030303030303031"
        ).encode()
    )
    frame = decode_frame(raw)
    assert frame == Frame("data", 1, payload, raw=raw)
    assert serialize_frame(frame) == raw
    assert serialize_frame(Frame("data", 1, payload)) == raw


@pytest.mark.parametrize("filename", ["空.bin", "中文,带,逗号.exe", "data.pdf"])
@pytest.mark.parametrize("chunk_size", [1, 1400, CHUNK_SIZE, MAX_CHUNK_SIZE])
def test_start_metadata(filename, chunk_size):
    meta = {"filename": filename, "md5": "a" * 32, "total_packets": 42, "chunk_size": chunk_size}
    raw = encode_start(meta)
    assert raw.endswith(b"3838383838383838")
    assert bytes.fromhex(raw[:-48].decode()) == f"{filename},{'A' * 32},42,{chunk_size}".encode()
    frame = decode_frame(raw)
    assert frame.metadata == dict(meta, md5="A" * 32, version=2, file_size=None)
    assert serialize_frame(frame) == raw
    assert serialize_frame(Frame("start", START_ID, b"", meta)) == raw


def test_default_chunk_size_and_finish():
    meta = {"filename": "empty", "md5": "A" * 32, "total_packets": 0}
    assert decode_frame(encode_start(meta)).metadata["chunk_size"] == 2100
    assert decode_frame(encode_finish()).kind == "finish"
    assert encode_finish().endswith(b"3939393939393939")
    assert serialize_frame(Frame("finish", FINISH_ID, b"")) == encode_finish()


@pytest.mark.parametrize("packet_id", [-1, START_ID, FINISH_ID, 100_000_000, True])
def test_invalid_data_ids(packet_id):
    with pytest.raises(ProtocolError):
        encode_data(packet_id, b"x")


@pytest.mark.parametrize("chunk_size", [-1, 0, MAX_CHUNK_SIZE + 1, True, "2100"])
def test_invalid_start_chunk_size(chunk_size):
    with pytest.raises(ProtocolError):
        encode_start(
            {"filename": "x", "md5": "A" * 32, "total_packets": 1, "chunk_size": chunk_size}
        )


@pytest.mark.parametrize("payload", [b"", b"x" * (MAX_CHUNK_SIZE + 1)])
def test_invalid_data_size(payload):
    with pytest.raises(ProtocolError):
        encode_data(0, payload)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"A" * 49,
        b"G" * 50,
        encode_data(0, b"x").lower(),
        encode_data(0, b"x")[:-48] + b"0" * 32 + encode_data(0, b"x")[-16:],
        encode_data(0, b"x")[:-16] + b"4141414141414141",
        wrap_v2(b"x", 88888889),
        wrap_v2(b"Finish", FINISH_ID),
        wrap_v2(b"name,notmd5,1,2100", START_ID),
        wrap_v2(b"name," + b"A" * 32 + b",-1,2100", START_ID),
        wrap_v2(b"name," + b"A" * 32 + b",88888889,2100", START_ID),
        wrap_v2(b"\xff," + b"A" * 32 + b",0,2100", START_ID),
        wrap_v2(b"name," + b"A" * 32 + b",1", START_ID),
        wrap_v2(b"name," + b"A" * 32 + b",1,QRFT2100", START_ID),
        wrap_v2(b"name," + b"A" * 32 + b",1,2125", START_ID),
    ],
)
def test_invalid_frames(raw):
    with pytest.raises(ProtocolError):
        decode_frame(raw)


def test_legacy_crc_frames_rejected():
    body, suffix = b"legacy data", b"00000000"
    legacy = body + zlib.crc32(body + suffix).to_bytes(4, "big") + suffix
    with pytest.raises(ProtocolError):
        decode_frame(legacy)
    with pytest.raises(ProtocolError):
        serialize_frame(Frame("data", 0, body, version=1, raw=legacy))


def test_text_input_rejected():
    with pytest.raises(TypeError):
        decode_frame("text")

import pytest

from qrft.core.protocol import (
    FINISH_ID,
    START_ID,
    ProtocolError,
    decode_frame,
    encode_data,
    encode_finish,
    encode_start,
)


@pytest.mark.parametrize("payload", [b"", b"\x00\xff\x80", bytes(range(256)), b"00000001"])
def test_binary_data_roundtrip(payload: bytes) -> None:
    raw = encode_data(12, payload)
    assert raw.endswith(b"00000012")
    result = decode_frame(raw)
    assert (result.kind, result.packet_id, result.payload) == ("data", 12, payload)


def test_control_roundtrip() -> None:
    metadata = {"filename": "文件.cst", "sha256": "abcd", "size": 10}
    assert decode_frame(encode_start(metadata)).metadata == metadata
    assert decode_frame(encode_finish()).kind == "finish"


def test_corrupt_payload_rejected() -> None:
    frame = bytearray(encode_data(1, b"\x00\xff"))
    frame[0] ^= 1
    with pytest.raises(ProtocolError, match="CRC32"):
        decode_frame(bytes(frame))


@pytest.mark.parametrize("packet_id", [-1, START_ID, FINISH_ID, 100_000_000])
def test_invalid_packet_ids(packet_id: int) -> None:
    with pytest.raises(ProtocolError):
        encode_data(packet_id, b"hello")


def test_invalid_suffix() -> None:
    with pytest.raises(ProtocolError):
        decode_frame(b"data" + b"\x00" * 4 + b"0000000x")


def test_text_input_rejected() -> None:
    with pytest.raises(TypeError):
        decode_frame("text")  # type: ignore[arg-type]

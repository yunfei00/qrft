"""QRFT v2: uppercase content HEX, content MD5 HEX and decimal-ASCII ID HEX."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

START_ID = 88_888_888
FINISH_ID = 99_999_999
MAX_ID = 99_999_999
CHUNK_SIZE = 2100
MAX_CHUNK_SIZE = 2124
_HEX = re.compile(rb"[0-9A-F]*")
_MD5 = re.compile(r"[0-9A-F]{32}")
_PACKET_ID = re.compile(rb"[0-9]{8}")


class ProtocolError(ValueError):
    """Invalid, corrupt or unsupported QRFT frame."""


@dataclass(frozen=True)
class Frame:
    kind: str
    packet_id: int
    payload: bytes
    metadata: dict[str, Any] | None = None
    version: int = 2
    raw: bytes | None = None


def validate_chunk_size(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_CHUNK_SIZE:
        raise ProtocolError(f"chunk size must be 1..{MAX_CHUNK_SIZE} bytes")
    return value


def _packet_id(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= MAX_ID:
        raise ProtocolError("packet ID must be an integer of at most eight decimal digits")
    return f"{value:08d}".encode("ascii")


def wrap_v2(content: bytes, packet_id: int) -> bytes:
    return (
        content.hex().upper()
        + hashlib.md5(content, usedforsecurity=False).hexdigest().upper()
        + _packet_id(packet_id).hex().upper()
    ).encode("ascii")


def encode_data(packet_id: int, payload: bytes) -> bytes:
    if type(packet_id) is not int or not 0 <= packet_id < START_ID:
        raise ProtocolError("v2 DATA ID outside contiguous range")
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_CHUNK_SIZE:
        raise ProtocolError(f"v2 DATA requires 1..{MAX_CHUNK_SIZE} original bytes")
    return wrap_v2(payload, packet_id)


def encode_start(metadata: dict[str, Any]) -> bytes:
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")
    if metadata.get("version", 2) != 2:
        raise ProtocolError("only protocol v2 is supported")
    filename = metadata.get("filename")
    md5 = metadata.get("md5")
    total = metadata.get("total_packets")
    chunk = validate_chunk_size(metadata.get("chunk_size", CHUNK_SIZE))
    if not isinstance(filename, str) or not filename or "\x00" in filename:
        raise ProtocolError("v2 filename missing or contains NUL")
    if not isinstance(md5, str) or _MD5.fullmatch(md5.upper()) is None:
        raise ProtocolError("invalid file MD5")
    if type(total) is not int or not 0 <= total <= START_ID:
        raise ProtocolError("invalid total block count")
    return wrap_v2(f"{filename},{md5.upper()},{total},{chunk}".encode(), START_ID)


def encode_finish() -> bytes:
    return wrap_v2(b"finish", FINISH_ID)


def decode_frame(raw: bytes) -> Frame:
    if not isinstance(raw, bytes):
        raise TypeError("QR decoder must return raw bytes, not text")
    if len(raw) < 48 or len(raw) % 2 or _HEX.fullmatch(raw) is None:
        raise ProtocolError("v2 requires even-length uppercase HEX and 48 suffix characters")
    suffix = bytes.fromhex(raw[-16:].decode("ascii"))
    if _PACKET_ID.fullmatch(suffix) is None:
        raise ProtocolError("v2 ID must encode eight decimal ASCII digits")
    packet_id = int(suffix)
    payload = bytes.fromhex(raw[:-48].decode("ascii"))
    digest = hashlib.md5(payload, usedforsecurity=False).hexdigest().upper().encode("ascii")
    if digest != raw[-48:-16]:
        raise ProtocolError("v2 content MD5 mismatch")
    if packet_id == START_ID:
        try:
            filename, md5, count, chunk_text = payload.decode("utf-8").rsplit(",", 3)
        except (UnicodeError, ValueError) as exc:
            raise ProtocolError("invalid v2 START text") from exc
        if (
            not filename
            or "\x00" in filename
            or _MD5.fullmatch(md5) is None
            or re.fullmatch(r"[0-9]+", count) is None
            or len(count) > 8
            or int(count) > START_ID
            or re.fullmatch(r"[0-9]{1,4}", chunk_text) is None
        ):
            raise ProtocolError("invalid v2 START fields")
        metadata = {
            "version": 2,
            "filename": filename,
            "md5": md5,
            "total_packets": int(count),
            "chunk_size": validate_chunk_size(int(chunk_text)),
            "file_size": None,
        }
        return Frame("start", packet_id, b"", metadata, raw=raw)
    if packet_id == FINISH_ID:
        if payload != b"finish":
            raise ProtocolError("v2 FINISH content must be lowercase finish")
        return Frame("finish", packet_id, b"", raw=raw)
    if not 0 <= packet_id < START_ID or not 1 <= len(payload) <= MAX_CHUNK_SIZE:
        raise ProtocolError("invalid v2 DATA ID or block size")
    return Frame("data", packet_id, payload, raw=raw)


def serialize_frame(frame: Frame) -> bytes:
    if frame.version != 2:
        raise ProtocolError("only protocol v2 is supported")
    if frame.raw is not None:
        decode_frame(frame.raw)
        return frame.raw
    if frame.kind == "start":
        return encode_start(frame.metadata or {})
    if frame.kind == "finish":
        return encode_finish()
    if frame.kind == "data":
        return encode_data(frame.packet_id, frame.payload)
    raise ProtocolError("unknown frame kind")


encode_data_v2 = encode_data
encode_start_v2 = encode_start
encode_finish_v2 = encode_finish
decode_v2 = decode_frame

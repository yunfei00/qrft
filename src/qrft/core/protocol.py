"""Version 1 QRFT binary framing.

Wire format:
DATA:   payload || crc32_be(payload || packet_id_ascii) || packet_id_ascii
START:  b"QRFT1S" || compact_utf8_json || crc32_be(prefix) || b"88888888"
FINISH: b"QRFT1F" || crc32_be(prefix) || b"99999999"

A control packet can only be interpreted as control when its reserved packet ID is present.
"""
from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from typing import Any

START_ID = 88_888_888
FINISH_ID = 99_999_999
MAX_ID = 99_999_999
START_MAGIC = b"QRFT1S"
FINISH_MAGIC = b"QRFT1F"
_PACKET_ID_RE = re.compile(rb"[0-9]{8}")


class ProtocolError(ValueError):
    """Invalid, corrupt or unsupported QRFT frame."""


@dataclass(frozen=True)
class Frame:
    kind: str
    packet_id: int
    payload: bytes
    metadata: dict[str, Any] | None = None


def _packet_id(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolError("packet ID must be an integer")
    if not 0 <= value <= MAX_ID:
        raise ProtocolError("packet ID exceeds eight decimal digits")
    return f"{value:08d}".encode("ascii")


def _crc(data: bytes) -> bytes:
    return (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "big")


def _wrap(body: bytes, packet_id: int) -> bytes:
    suffix = _packet_id(packet_id)
    return body + _crc(body + suffix) + suffix


def encode_data(packet_id: int, payload: bytes) -> bytes:
    """Encode arbitrary file bytes; control IDs are never valid DATA IDs."""
    if packet_id in (START_ID, FINISH_ID):
        raise ProtocolError("reserved packet ID")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    return _wrap(payload, packet_id)


def encode_start(metadata: dict[str, Any]) -> bytes:
    """Emit a compact metadata control frame.

    Large manifests will require protocol extension; no silent truncation is allowed.
    """
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")
    try:
        raw = json.dumps(
            metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("metadata is not JSON serializable") from exc
    return _wrap(START_MAGIC + raw, START_ID)


def encode_finish() -> bytes:
    return _wrap(FINISH_MAGIC, FINISH_ID)


def decode_frame(raw: bytes) -> Frame:
    if not isinstance(raw, bytes):
        raise TypeError("QR decoder must return raw bytes, not text")
    if len(raw) < 12:
        raise ProtocolError("frame too short")
    suffix = raw[-8:]
    if _PACKET_ID_RE.fullmatch(suffix) is None:
        raise ProtocolError("frame must end in eight ASCII decimal digits")
    packet_id = int(suffix)
    body, checksum = raw[:-12], raw[-12:-8]
    if checksum != _crc(body + suffix):
        raise ProtocolError("CRC32 mismatch")
    if packet_id == START_ID:
        if not body.startswith(START_MAGIC):
            raise ProtocolError("invalid START magic")
        try:
            metadata = json.loads(body[len(START_MAGIC):].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("invalid START metadata") from exc
        if not isinstance(metadata, dict):
            raise ProtocolError("START metadata must be a JSON object")
        return Frame("start", packet_id, b"", metadata)
    if packet_id == FINISH_ID:
        if body != FINISH_MAGIC:
            raise ProtocolError("invalid FINISH magic")
        return Frame("finish", packet_id, b"")
    return Frame("data", packet_id, body)

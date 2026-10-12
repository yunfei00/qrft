"""Frozen v2: uppercase content HEX + raw-content MD5 HEX + decimal-ASCII ID HEX."""

import hashlib
import re

from .protocol import FINISH_ID, START_ID, Frame, ProtocolError, _packet_id

CHUNK_SIZE = 1400
HEX = re.compile(rb"[0-9A-F]*")
MD5 = re.compile(r"[0-9A-F]{32}")


def wrap_v2(content: bytes, packet_id: int) -> bytes:
    return (
        content.hex().upper()
        + hashlib.md5(content, usedforsecurity=False).hexdigest().upper()
        + _packet_id(packet_id).hex().upper()
    ).encode("ascii")


def encode_data_v2(packet_id: int, payload: bytes) -> bytes:
    if not 0 <= packet_id < START_ID:
        raise ProtocolError("v2 DATA ID outside contiguous range")
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= CHUNK_SIZE:
        raise ProtocolError("v2 DATA requires 1..1400 original bytes")
    return wrap_v2(payload, packet_id)


def encode_start_v2(meta: dict) -> bytes:
    filename, md5, total = meta.get("filename"), meta.get("md5"), meta.get("total_packets")
    if not isinstance(filename, str) or not filename or "\x00" in filename:
        raise ProtocolError("v2 filename missing or contains NUL")
    if not isinstance(md5, str) or MD5.fullmatch(md5.upper()) is None:
        raise ProtocolError("invalid file MD5")
    if type(total) is not int or not 0 <= total <= START_ID:
        raise ProtocolError("invalid total block count")
    return wrap_v2(f"{filename},{md5.upper()},{total}".encode(), START_ID)


def encode_finish_v2() -> bytes:
    return wrap_v2(b"finish", FINISH_ID)


def decode_v2(raw: bytes) -> Frame:
    if len(raw) < 48 or len(raw) % 2 or HEX.fullmatch(raw) is None:
        raise ProtocolError("v2 requires even-length uppercase HEX and 48 suffix characters")
    suffix = bytes.fromhex(raw[-16:].decode("ascii"))
    if re.fullmatch(rb"[0-9]{8}", suffix) is None:
        raise ProtocolError("v2 ID must encode eight decimal ASCII digits")
    packet_id = int(suffix)
    payload = bytes.fromhex(raw[:-48].decode("ascii"))
    if hashlib.md5(payload, usedforsecurity=False).hexdigest().upper().encode() != raw[-48:-16]:
        raise ProtocolError("v2 content MD5 mismatch")
    if packet_id == START_ID:
        try:
            filename, md5, count = payload.decode("utf-8").rsplit(",", 2)
        except (UnicodeError, ValueError) as exc:
            raise ProtocolError("invalid v2 START text") from exc
        if (
            not filename
            or "\x00" in filename
            or MD5.fullmatch(md5) is None
            or re.fullmatch(r"[0-9]+", count) is None
            or len(count) > 8
            or int(count) > START_ID
        ):
            raise ProtocolError("invalid v2 START fields")
        meta = {
            "version": 2,
            "filename": filename,
            "md5": md5,
            "total_packets": int(count),
            "chunk_size": CHUNK_SIZE,
            "file_size": None,
        }
        return Frame("start", packet_id, b"", meta, 2, raw)
    if packet_id == FINISH_ID:
        if payload != b"finish":
            raise ProtocolError("v2 FINISH content must be lowercase finish")
        return Frame("finish", packet_id, b"", None, 2, raw)
    if not 0 <= packet_id < START_ID or not 1 <= len(payload) <= CHUNK_SIZE:
        raise ProtocolError("invalid v2 DATA ID or block size")
    return Frame("data", packet_id, payload, None, 2, raw)

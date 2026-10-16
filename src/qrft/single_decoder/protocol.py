"""Use the shared v2 parser for durable project receipts."""

import hashlib
import json

from qrft.core.protocol import decode_frame


def filename(value):
    if (
        not value
        or value in (".", "..")
        or value[-1] in ". "
        or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in value)
        or value.split(".", 1)[0].rstrip(" ").upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "CONIN$",
            "CONOUT$",
            *(f"COM{i}" for i in "¹²³"),
            *(f"LPT{i}" for i in "¹²³"),
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise ValueError("Unsafe Windows output filename")
    return value


def parse(raw):
    raw = raw.encode("ascii") if isinstance(raw, str) else raw
    frame = decode_frame(raw)
    payload = bytes.fromhex(raw[:-48].decode("ascii"))
    if frame.kind != "start":
        return frame.packet_id, payload, None
    meta = frame.metadata
    return (
        frame.packet_id,
        payload,
        {
            "protocol": "V2",
            "filename": filename(meta["filename"]),
            "expected_md5": meta["md5"],
            "total_packets": meta["total_packets"],
            "chunk_size": meta["chunk_size"],
        },
    )


def identity(meta):
    return hashlib.sha256(
        json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def valid_data(meta, number, payload):
    total = meta["total_packets"]
    return 0 <= number < total and (
        len(payload) == meta["chunk_size"]
        if number < total - 1
        else 1 <= len(payload) <= meta["chunk_size"]
    )

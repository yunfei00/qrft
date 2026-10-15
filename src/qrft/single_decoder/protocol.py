"""Adapt existing strict parsers, without changing either frozen wire format."""

import hashlib
import json

from qrft.core.protocol_v2 import decode_v2
from qrft.encoder2100.protocol import START_ID, inspect_frame


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
    text = raw.decode("ascii") if isinstance(raw, bytes) else raw
    try:
        number, payload = inspect_frame(text)
    except ValueError:
        # Only an old v2 START differs; DATA and FINISH have the same strict envelope.
        old = decode_v2(text.encode("ascii"))
        if old.kind != "start":
            raise ValueError("Invalid V2 frame") from None
        meta = old.metadata
        return (
            START_ID,
            bytes.fromhex(text[:-48]),
            {
                "protocol": "V2",
                "filename": filename(meta["filename"]),
                "expected_md5": meta["md5"],
                "total_packets": meta["total_packets"],
                "chunk_size": 1400,
            },
        )
    if number != START_ID:
        return number, payload, None
    name, md5, count, marker = payload.decode("utf-8").rsplit(",", 3)
    return (
        number,
        payload,
        {
            "protocol": marker,
            "filename": filename(name),
            "expected_md5": md5,
            "total_packets": int(count),
            "chunk_size": 2100,
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

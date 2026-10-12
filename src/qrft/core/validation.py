"""Shared task manifest and payload checks; v2 does not invent a wire file size/SHA256."""

from .protocol import START_ID, Frame, ProtocolError


def validate_manifest(meta: dict) -> None:
    version = meta.get("version", 1)
    size, chunk, total = (meta.get(k) for k in ("file_size", "chunk_size", "total_packets"))
    if type(total) is not int or not 0 <= total <= START_ID:
        raise ProtocolError("invalid START manifest sizes")
    if version == 2:
        if chunk != 1400 or size is not None:
            raise ProtocolError("invalid v2 manifest")
        hashes = (("md5", 32),)
    elif version == 1:
        if (
            type(size) is not int
            or type(chunk) is not int
            or size < 0
            or chunk <= 0
            or total != (size + chunk - 1) // chunk
        ):
            raise ProtocolError("invalid START manifest sizes")
        hashes = (("md5", 32), ("sha256", 64))
    else:
        raise ProtocolError("unsupported manifest version")
    if not all(
        isinstance(meta.get(k), str)
        and len(meta[k]) == n
        and all(c in "0123456789abcdefABCDEF" for c in meta[k])
        for k, n in hashes
    ):
        raise ProtocolError("invalid manifest hashes")


def validate_data(meta: dict, frame: Frame) -> None:
    if frame.version != meta.get("version", 1):
        raise ProtocolError("protocol version mismatch: cannot mix v1 and v2")
    total, chunk = meta["total_packets"], meta["chunk_size"]
    if frame.kind != "data" or not 0 <= frame.packet_id < total:
        raise ProtocolError("packet ID outside manifest")
    if frame.version == 2:
        valid = (
            len(frame.payload) == chunk
            if frame.packet_id < total - 1
            else 1 <= len(frame.payload) <= chunk
        )
    else:
        valid = len(frame.payload) == min(chunk, meta["file_size"] - frame.packet_id * chunk)
    if not valid:
        raise ProtocolError("incorrect packet length")

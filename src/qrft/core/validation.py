"""Validate v2 metadata and file blocks."""

from .protocol import START_ID, Frame, ProtocolError, validate_chunk_size


def validate_manifest(meta: dict) -> None:
    if meta.get("version", 2) != 2:
        raise ProtocolError("only protocol v2 is supported")
    validate_chunk_size(meta.get("chunk_size"))
    total = meta.get("total_packets")
    if type(total) is not int or not 0 <= total <= START_ID or meta.get("file_size") is not None:
        raise ProtocolError("invalid v2 manifest sizes")
    filename, md5 = meta.get("filename"), meta.get("md5")
    if not isinstance(filename, str) or not filename or "\x00" in filename:
        raise ProtocolError("invalid manifest filename")
    if (
        not isinstance(md5, str)
        or len(md5) != 32
        or any(c not in "0123456789abcdefABCDEF" for c in md5)
    ):
        raise ProtocolError("invalid manifest MD5")


def validate_data(meta: dict, frame: Frame) -> None:
    if frame.version != 2 or meta.get("version", 2) != 2:
        raise ProtocolError("only protocol v2 is supported")
    total, chunk = meta["total_packets"], meta["chunk_size"]
    if frame.kind != "data" or not 0 <= frame.packet_id < total:
        raise ProtocolError("packet ID outside manifest")
    valid = (
        len(frame.payload) == chunk
        if frame.packet_id < total - 1
        else 1 <= len(frame.payload) <= chunk
    )
    if not valid:
        raise ProtocolError("incorrect packet length")

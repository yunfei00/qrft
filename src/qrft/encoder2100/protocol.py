"""QRFT2100 frozen wire format. No dependency on the older protocols."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

CHUNK_SIZE = 2100
START_ID = 88888888
FINISH_ID = 99999999
PROTOCOL = "QRFT2100"
HEX = re.compile(r"[0-9A-F]*\Z")


def frame(content: bytes, packet_id: int) -> str:
    if not 0 <= packet_id < START_ID and packet_id not in (START_ID, FINISH_ID):
        raise ValueError("非法包号")
    return (
        content.hex().upper()
        + hashlib.md5(content).hexdigest().upper()
        + f"{packet_id:08d}".encode("ascii").hex().upper()
    )


def data_frame(content: bytes, packet_id: int) -> str:
    if not 0 <= packet_id < START_ID or not 1 <= len(content) <= CHUNK_SIZE:
        raise ValueError("DATA 必须为 1～2100 字节且编号不占用控制帧")
    text = frame(content, packet_id)
    assert len(text) == 2 * len(content) + 48
    return text


@dataclass(frozen=True)
class Metadata:
    name: str
    size: int
    md5: str
    packets: int

    def start(self) -> str:
        return frame(f"{self.name},{self.md5},{self.packets},{PROTOCOL}".encode(), START_ID)


def inspect_frame(text: str) -> tuple[int, bytes]:
    """Strict independent-encoder test inspector, not a file decoder."""
    if len(text) < 48 or len(text) % 2 or not HEX.fullmatch(text):
        raise ValueError("非法 HEX 帧")
    number = bytes.fromhex(text[-16:])
    if len(number) != 8 or any(c < 48 or c > 57 for c in number):
        raise ValueError("非法 ASCII 包号")
    packet_id = int(number)
    content = bytes.fromhex(text[:-48])
    if hashlib.md5(content).hexdigest().upper() != text[-48:-16]:
        raise ValueError("内容 MD5 不一致")
    if packet_id == START_ID:
        try:
            name, digest, count, protocol = content.decode("utf-8").rsplit(",", 3)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("非法 START") from exc
        if (
            not name
            or not re.fullmatch(r"[0-9A-F]{32}", digest)
            or not re.fullmatch(r"0|[1-9][0-9]*", count)
            or int(count) > START_ID
            or protocol != PROTOCOL
        ):
            raise ValueError("非法 START 元数据")
    elif packet_id == FINISH_ID:
        if content != b"finish":
            raise ValueError("非法 FINISH")
    elif packet_id >= START_ID or not 1 <= len(content) <= CHUNK_SIZE:
        raise ValueError("非法 DATA")
    return packet_id, content

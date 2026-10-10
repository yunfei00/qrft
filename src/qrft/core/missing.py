"""缺包统计与导出：可直接复用于编码端补传。"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from .protocol import START_ID, ProtocolError


def missing_ids(total_packets: int, received_ids: Iterable[int]) -> list[int]:
    """返回全部缺失的 DATA 包号（按升序）。"""
    if total_packets < 0 or total_packets > START_ID:
        raise ProtocolError("无效的 DATA 包总数")
    received = set(received_ids)
    if any(not isinstance(i, int) or i < 0 or i >= total_packets for i in received):
        raise ProtocolError("已接收包号超出范围")
    return sorted(set(range(total_packets)) - received)


def format_missing_txt(ids: Iterable[int]) -> str:
    """每行 8 位包号，兼容 parse_packet_list。"""
    return "".join(f"{packet_id:08d}\n" for packet_id in ids)


def export_missing(directory: Path, total_packets: int, received_ids: Iterable[int]) -> list[int]:
    """每次解码尝试均更新三种缺包文件，包括零缺包的情况。"""
    directory.mkdir(parents=True, exist_ok=True)
    ids = missing_ids(total_packets, received_ids)
    (directory / "missing.txt").write_text(format_missing_txt(ids), encoding="ascii")
    with (directory / "missing.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["packet_id"])
        writer.writerows([[f"{packet_id:08d}"] for packet_id in ids])
    (directory / "missing.json").write_text(
        json.dumps(
            {"schema_version": 1, "total_packets": total_packets, "missing_ids": ids},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ids

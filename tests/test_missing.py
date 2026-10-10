import csv
import json
from pathlib import Path

import pytest

from qrft.core.manifest import parse_packet_list
from qrft.core.missing import export_missing, missing_ids
from qrft.core.protocol import ProtocolError


def test_missing_exports_reusable_for_retransmission(tmp_path: Path) -> None:
    assert export_missing(tmp_path, 5, [0, 2, 4, 4]) == [1, 3]
    text = (tmp_path / "missing.txt").read_text(encoding="ascii")
    assert parse_packet_list(text, 5) == [1, 3]
    with (tmp_path / "missing.csv").open(encoding="utf-8", newline="") as stream:
        assert list(csv.DictReader(stream)) == [
            {"packet_id": "00000001"},
            {"packet_id": "00000003"},
        ]
    data = json.loads((tmp_path / "missing.json").read_text(encoding="utf-8"))
    assert data["missing_ids"] == [1, 3]


def test_no_missing_still_writes_files(tmp_path: Path) -> None:
    assert export_missing(tmp_path, 2, [0, 1]) == []
    assert (tmp_path / "missing.txt").read_text() == ""
    assert (tmp_path / "missing.csv").exists()
    assert (tmp_path / "missing.json").exists()


def test_invalid_received_packet_rejected() -> None:
    with pytest.raises(ProtocolError):
        missing_ids(2, [3])

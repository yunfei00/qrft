"""CLI 导出与补传测试，需 encoder 可选依赖。"""

import json
from pathlib import Path

import pytest

from qrft.encoder_cli.main import export_frames


def test_export_all_frames(tmp_path: Path) -> None:
    pytest.importorskip("qrcode")
    source = tmp_path / "数据.bin"
    source.write_bytes(bytes(range(256)) + b"\x00\xff")
    output = tmp_path / "out"
    result = export_frames(source, output, chunk_size=128)
    assert result["total_packets"] == 3
    assert result["exported_data_packets"] == 3
    assert len(list(output.glob("*-data.png"))) == 3
    assert (output / "00000000-start.png").exists()
    assert (output / "99999999-finish.png").exists()
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["md5"]


def test_retransmit_selected_packets(tmp_path: Path) -> None:
    pytest.importorskip("qrcode")
    source = tmp_path / "sample.bin"
    source.write_bytes(bytes(range(20)))
    missing = tmp_path / "missing.txt"
    missing.write_text("00000001\n00000003\n", encoding="utf-8")
    output = tmp_path / "retry"
    result = export_frames(source, output, chunk_size=5, retransmit=missing)
    assert result["exported_data_packets"] == 2
    assert sorted(p.name for p in output.glob("*-data.png")) == [
        "00000001-data.png",
        "00000003-data.png",
    ]


def test_empty_file(tmp_path: Path) -> None:
    pytest.importorskip("qrcode")
    source = tmp_path / "empty"
    source.write_bytes(b"")
    result = export_frames(source, tmp_path / "out")
    assert result["total_packets"] == 0
    assert result["exported_data_packets"] == 0

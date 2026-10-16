"""编码器统一入口测试（不需要图形桌面）。"""

from pathlib import Path

import pytest

pytest.importorskip("qrcode")
pytest.importorskip("PIL")

from qrft.encoder_cli.entrypoint import main


def test_export_subcommand(tmp_path: Path) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"abcdef")
    output = tmp_path / "frames"
    assert main(["export", str(source), "--output", str(output), "--chunk-size", "2"]) == 0
    assert len(list(output.glob("*-data.png"))) == 3
    assert (output / "manifest.json").exists()


def test_requires_subcommand() -> None:
    assert main([]) == 0  # No-argument launch shows full usage help.

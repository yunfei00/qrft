"""Real frozen CLI gate and authenticated PNG export; no stdin-pipe bypass."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from qrft.encoder_cli.console_test import run_encoder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    exe = args.exe.resolve()
    with tempfile.TemporaryDirectory(prefix="qrft-encoder-gate-") as directory:
        root = Path(directory)
        source = root / "中文,样本.bin"
        source.write_bytes(bytes(range(256)) * 6)
        for version in ("v1", "v2"):
            output = root / version
            command = [
                str(exe),
                "export",
                str(source),
                "--protocol",
                version,
                "--output",
                str(output),
            ]
            denied = subprocess.run(
                command, input="qsnfj\n", capture_output=True, text=True, timeout=20, check=False
            )
            assert denied.returncode != 0 and not output.exists()
            assert "usage:" not in denied.stdout + denied.stderr
            result = run_encoder(command, cwd=root, timeout=60)
            assert result.returncode == 0, result.stdout
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["md5"].upper() == hashlib.md5(source.read_bytes()).hexdigest().upper()
            assert len(list(output.glob("*-data.png"))) == (2 if version == "v2" else 6)
        for flag in ("-h", "--help", "--unknown"):
            result = run_encoder([str(exe), flag], cwd=root)
            assert result.returncode != 0
            assert "usage:" not in result.stdout and "export" not in result.stdout
        print("PASS: frozen CLI terminal gate, v1/v2 export and MD5; no help leakage")


if __name__ == "__main__":
    main()

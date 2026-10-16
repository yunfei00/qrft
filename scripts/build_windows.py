"""Build the three supported Windows applications with one configuration."""

import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != "win32":
        raise RuntimeError("Build Windows applications on Windows")
    root = Path(__file__).resolve().parents[1]
    applications = (
        ("QRFT-Encoder-CLI", "encoder_cli/entrypoint.py"),
        ("QRFT-Decoder", "decoder/entrypoint.py"),
        ("QRFT-Control", "control/app.py"),
    )
    for name, entrypoint in applications:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onedir",
                "--console",
                "--name",
                name,
                "--paths",
                "src",
                "--specpath",
                "build",
                *(["--exclude-module", "PySide6"] if name == "QRFT-Encoder-CLI" else []),
                f"src/qrft/{entrypoint}",
            ],
            cwd=root,
            check=True,
        )


if __name__ == "__main__":
    main()

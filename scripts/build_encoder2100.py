"""Build only the independent Windows console encoder and its release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

VERSION = "0.1.0"
PRODUCT = "QRFT-Encoder2100"
REPO = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(root):
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Windows x64 build required")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--noupx",
        "--name",
        PRODUCT,
        "--paths",
        str(REPO / "src"),
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "work"),
        "--specpath",
        str(root),
    ]
    for name in (
        "PySide6",
        "PyQt5",
        "PyQt6",
        "tkinter",
        "pytest",
        "httpx",
        "fastapi",
        "uvicorn",
        "zxingcpp",
        "winpty",
        "psutil",
        "qrft.encoder_cli",
        "qrft.encoder_gui",
        "qrft.decoder",
        "qrft.decoder_gui",
        "qrft.control",
        "qrft.acceptance",
    ):
        command.extend(["--exclude-module", name])
    command.append(str(REPO / "src/qrft/encoder2100/entrypoint.py"))
    subprocess.run(command, cwd=REPO, check=True)
    from PyInstaller.archive.readers import ZlibArchiveReader

    modules = ZlibArchiveReader(str(root / "work" / PRODUCT / "PYZ-00.pyz")).toc
    forbidden = (
        "qrft.decoder",
        "qrft.control",
        "qrft.encoder_cli",
        "qrft.encoder_gui",
        "qrft.acceptance",
        "PySide6",
    )
    assert not any(name.startswith(forbidden) for name in modules)
    assert "qrft.encoder2100.cli" in modules and "qrft.encoder2100.player" in modules
    product = root / "dist" / PRODUCT
    shutil.copyfile(REPO / "docs/ENCODER_2100_DISTRIBUTION_README.md", product / "README.md")
    shutil.copyfile(REPO / "docs/ENCODER_2100_USER_GUIDE.md", product / "USER_GUIDE.md")
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        if (REPO / name).is_file():
            shutil.copyfile(REPO / name, product / name)
    version = {
        "product": PRODUCT,
        "version": VERSION,
        "tag": f"encoder2100-v{VERSION}",
        "commit": commit,
        "python": platform.python_version(),
        "pyinstaller": importlib.metadata.version("pyinstaller"),
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "architecture": "Windows x64",
        "entrypoint": "qrft.encoder2100.entrypoint -> qrft.encoder2100.cli",
    }
    (product / "VERSION.txt").write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
    checksums = [
        f"{sha256(path)}  {path.relative_to(product).as_posix()}"
        for path in sorted(product.rglob("*"))
        if path.is_file()
    ]
    (product / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    archive = root / f"{PRODUCT}-Windows-x64-v{VERSION}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(product.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(
                    f"{PRODUCT}/{path.relative_to(product).as_posix()}", (1980, 1, 1, 0, 0, 0)
                )
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                info._compresslevel = 6
                with path.open("rb") as source, zipped.open(info, "w") as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
    digest = sha256(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    (root / "build.json").write_text(
        json.dumps(
            {
                **version,
                "zip": archive.name,
                "zip_sha256": digest,
                "zip_bytes": archive.stat().st_size,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"archive": str(archive), "sha256": digest}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    build(parser.parse_args().root)

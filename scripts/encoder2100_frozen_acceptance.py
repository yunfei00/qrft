"""Verify the actual release ZIP in an isolated CWD/PATH, through real ConPTY input.

This is a developer-only driver, never included in the encoder. Native Space/Esc
actions are performed separately with Computer Use; this script does not inject UI.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import os
import random
import re
import struct
import subprocess
import threading
import time
import zipfile
from pathlib import Path

import psutil

PRODUCT = "QRFT-Encoder2100"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def isolated_env():
    env = dict(os.environ)
    for key in list(env):
        if key.upper().startswith(("PYTHON", "UV_", "VIRTUAL_ENV", "QT_", "_PYI")):
            env.pop(key)
    env["SystemRoot"] = os.environ["SystemRoot"]
    env["PATH"] = str(Path(env["SystemRoot"]) / "System32")
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


class Terminal:
    def __init__(self, command, cwd):
        from winpty import PtyProcess

        self.env = isolated_env()
        self.process = PtyProcess.spawn(list(map(str, command)), cwd=str(cwd), env=self.env)
        self.parts = []
        self.received = []
        self.records = {}
        self.done = threading.Event()
        self.started = time.monotonic()

        def collect():
            try:
                while True:
                    value = self.process.read()
                    self.parts.append(value)
                    self.received.append(
                        {"seconds": time.monotonic() - self.started, "text": value}
                    )
            except (EOFError, OSError):
                pass

        def monitor():
            while not self.done.is_set():
                try:
                    parent = psutil.Process(self.process.pid)
                    for process in [parent, *parent.children(recursive=True)]:
                        try:
                            record = self.records.setdefault(
                                process.pid,
                                {
                                    "pid": process.pid,
                                    "exe": process.exe(),
                                    "command": process.cmdline(),
                                    "rss_peak": 0,
                                },
                            )
                            record["rss_peak"] = max(record["rss_peak"], process.memory_info().rss)
                            if time.monotonic() - record.get("last_module_scan", 0) >= 1:
                                record["modules"] = sorted(
                                    set(record.get("modules", []))
                                    | {m.path for m in process.memory_maps()}
                                )
                                record["last_module_scan"] = time.monotonic()
                        except psutil.Error:
                            pass
                except psutil.Error:
                    pass
                self.done.wait(0.1)

        self.reader = threading.Thread(target=collect, daemon=True)
        self.reader.start()
        self.monitor = threading.Thread(target=monitor, daemon=True)
        self.monitor.start()

    def text(self):
        return ANSI.sub("", "".join(self.parts)).replace("\r", "")

    def finish(self, inputs=("qsnfj",), timeout=120):
        # Frozen startup is allowed time to reach getpass before typing.
        time.sleep(1.5)
        silent = self.text().strip() == ""
        for value in inputs:
            if self.process.isalive():
                self.process.write(value + "\r")
                time.sleep(0.25)
        try:
            while self.process.isalive():
                if time.monotonic() - self.started > timeout:
                    raise TimeoutError("Frozen terminal acceptance timed out")
                time.sleep(0.05)
            self.reader.join(timeout=2)
            raw = self.text()
            assert all(not value or value not in raw for value in inputs), "Terminal input echoed"
            return {
                "returncode": self.process.exitstatus,
                "stdout": raw,
                "silent_before_input": silent,
                "hidden_input": True,
                "processes": list(self.records.values()),
                "output_events": self.received,
            }
        finally:
            self.done.set()
            self.process.close(force=True)
            self.monitor.join(timeout=2)
            self.reader.join(timeout=2)


def read_png(path):
    import zxingcpp
    from PIL import Image

    with Image.open(path) as picture:
        assert picture.size == (925, 925)
        result = zxingcpp.read_barcode(picture)
    assert result is not None, path
    text = result.text
    assert set(text) <= set("0123456789ABCDEF")
    payload = bytes.fromhex(text[:-48])
    assert hashlib.md5(payload).hexdigest().upper() == text[-48:-16]
    return int(bytes.fromhex(text[-16:])), payload


def snapshot(folder):
    return {
        p.relative_to(folder).as_posix(): None if p.is_dir() else digest(p)
        for p in folder.rglob("*")
    }


def run(archive, root):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "RUNNING", "zip_sha256": digest(archive), "checks": [], "commands": []}
    try:
        assert (
            archive.with_suffix(".zip.sha256").read_text(encoding="ascii").split()[0]
            == report["zip_sha256"]
        )
        with zipfile.ZipFile(archive) as zipped:
            for name in zipped.namelist():
                parts = Path(name).parts
                assert parts[0] == PRODUCT and not Path(name).is_absolute() and ".." not in parts
                assert not any(x in parts for x in (".venv", "__pycache__", "temp", ".env"))
                # Dependency license trees legitimately contain e.g. numpy/_core/src.
                assert len(parts) < 2 or parts[1] != "src"
            zipped.extractall(root / "解压 Fresh Space")
        bundle = root / "解压 Fresh Space" / PRODUCT
        runtime_zips = set(root.rglob("*.zip"))
        exe = bundle / f"{PRODUCT}.exe"
        assert exe.is_file() and (bundle / "_internal/python312.dll").is_file()
        for line in (bundle / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", 1)
            assert digest(bundle / name) == expected, name
        report["version"] = json.loads((bundle / "VERSION.txt").read_text(encoding="utf-8"))
        report["exe"] = str(exe)
        report["checks"].append("ZIP structure and every runtime file SHA256")
        env = isolated_env()
        assert all(
            subprocess.run(
                [str(Path(env["SystemRoot"]) / "System32/where.exe"), name],
                env=env,
                cwd=bundle,
                capture_output=True,
                check=False,
            ).returncode
            != 0
            for name in ("python", "uv")
        )
        report["path"] = env["PATH"]
        report["checks"].append("No Python/uv on child PATH; CWD contains no project/venv")

        def invoke(args, expected=0, inputs=("qsnfj",)):
            result = Terminal([exe, *args], bundle).finish(inputs=inputs)
            report["commands"].append({"args": list(map(str, args)), **result})
            assert result["returncode"] == expected, result
            assert result["silent_before_input"], "Application output before gate"
            return result["stdout"]

        fixture = root / "源 Folder 中文"
        (fixture / "Nested Space/空目录").mkdir(parents=True)
        (fixture / ".hidden").write_bytes(b"\x00\xffhidden")
        (fixture / "Zero.bin").write_bytes(b"")
        binary = fixture / "Nested Space/中文,#&[].EXE"
        binary.write_bytes(random.Random(2100).randbytes(4201))
        subprocess.run(["attrib", "+h", str(fixture / ".hidden")], check=True, env=env)
        before = snapshot(fixture)
        first = json.loads(invoke(["info", fixture]))
        second = json.loads(invoke(["info", fixture]))
        for path in fixture.rglob("*"):
            if path.is_file():
                os.utime(path, (1600000000, 1600000000))
        third = json.loads(invoke(["info", fixture]))
        fields = (
            "folder_content_md5",
            "folder_content_sha256",
            "archive_zip_md5",
            "archive_zip_sha256",
        )
        assert all(first[key] == second[key] == third[key] for key in fields)
        report["folder"] = first
        report["checks"].append("Folder/ZIP MD5 and SHA256 repeat + mtime stability")
        output = root / "PNG output"
        invoke(["export", fixture, "--output", output])
        parsed = dict(read_png(path) for path in output.glob("*.png"))
        packet_count = first["packets"]
        assert set(parsed) == {88888888, 99999999, *range(packet_count)}
        rebuilt = b"".join(parsed[i] for i in range(packet_count))
        assert hashlib.md5(rebuilt).hexdigest().upper() == first["archive_zip_md5"]
        assert hashlib.sha256(rebuilt).hexdigest().upper() == first["archive_zip_sha256"]
        name, md5, count, protocol = parsed[88888888].decode().rsplit(",", 3)
        assert (
            md5 == first["archive_zip_md5"]
            and int(count) == packet_count
            and protocol == "QRFT2100"
        )
        assert name.endswith(".zip") and parsed[99999999] == b"finish"
        with zipfile.ZipFile(io.BytesIO(rebuilt)) as zipped:
            restored = {
                n.rstrip("/"): None
                if n.endswith("/")
                else hashlib.sha256(zipped.read(n)).hexdigest()
                for n in zipped.namelist()
            }
            assert restored == before
            comment = json.loads(zipped.comment)
            assert comment["folder_content_md5"] == first["folder_content_md5"]
            logical_md5 = hashlib.md5(b"QRFT2100-FOLDER-CONTENT\x00\x01")
            logical_sha = hashlib.sha256(b"QRFT2100-FOLDER-CONTENT\x00\x01")
            for name in sorted(["", *restored], key=lambda value: value.encode("utf-8")):
                is_dir = not name or restored[name] is None
                content = b"" if is_dir else zipped.read(name)
                raw_name = name.encode("utf-8")
                serialized = (
                    (b"D" if is_dir else b"F")
                    + struct.pack(">Q", len(raw_name))
                    + raw_name
                    + struct.pack(">Q", len(content))
                    + content
                )
                logical_md5.update(serialized)
                logical_sha.update(serialized)
            assert logical_md5.hexdigest().upper() == first["folder_content_md5"]
            assert logical_sha.hexdigest().upper() == first["folder_content_sha256"]
        repeated_output = root / "Repeat PNG"
        invoke(["export", fixture, "--output", repeated_output])
        repeated = dict(read_png(path) for path in repeated_output.glob("*.png"))
        assert repeated == parsed
        report["repeated_zip_byte_exact"] = True
        report["png_count"] = len(parsed)
        report["checks"].append(
            "Actual frozen folder PNG -> independent ZXing -> ZIP byte hashes -> memory unzip"
        )
        retry = root / "Retry PNG"
        invoke(
            [
                "export",
                fixture,
                "--start-id",
                "0",
                "--end-id",
                "0",
                "--expected-archive-md5",
                first["archive_zip_md5"],
                "--output",
                retry,
            ]
        )
        assert read_png(retry / "00000000.png")[1] == parsed[0]
        for args in (
            ["--start-id", "1"],
            ["--start-id", "0", "--expected-archive-md5", "0" * 32],
        ):
            invoke(["export", fixture, *args, "--output", root / "must-not-exist"], expected=2)
            assert not (root / "must-not-exist").exists()
        report["checks"].append("Retransmission byte exact; missing/wrong original ZIP MD5 refused")
        invoke(["export", fixture, "--output", output], expected=2)
        invoke(["export", fixture, "--output", fixture / "forbidden"], expected=2)
        assert snapshot(fixture) == before
        report["checks"].append(
            "Source read-only; existing output and output-inside-source refused"
        )
        empty = root / "空 Folder"
        empty.mkdir()
        assert json.loads(invoke(["info", empty]))["file_count"] == 0
        zero = root / "empty.bin"
        zero.write_bytes(b"")
        zero_output = root / "zero PNG"
        invoke(["export", zero, "--output", zero_output])
        assert {p.name for p in zero_output.glob("*.png")} == {"88888888.png", "99999999.png"}
        long_folder = root / ("long path " * 7 + "End")
        long_folder.mkdir()
        long_input = long_folder / ("MiX name " * 6 + ".bin")
        long_input.write_bytes(bytes(range(256)))
        assert (
            json.loads(invoke(["info", long_input]))["md5"]
            == hashlib.md5(long_input.read_bytes()).hexdigest().upper()
        )
        report["checks"].append("Empty folder/file, Unicode/spaces/special names and long path")
        large = root / "Limit"
        large.mkdir()
        with (large / "Random.bin").open("xb") as stream:
            rng = random.Random(128)
            for _ in range(96):
                stream.write(rng.randbytes(65536))
        invoke(["info", large, "--max-archive-mib", "4"], expected=2)
        # PyInstaller includes its immutable Python base_library.zip runtime.
        assert set(root.rglob("*.zip")) == runtime_zips
        report["checks"].append("4 MiB RAM bound fails without temporary ZIP or disk fallback")
        invoke(
            ["export", binary, "--output", root / "denied-auth"],
            expected=1,
            inputs=("QSNFJ", "wrong", "incorrect"),
        )
        assert not (root / "denied-auth").exists()
        for option in ("-h", "--help", "--unknown"):
            invoke([option], expected=2)
        no_tty = subprocess.run(
            [exe, "info", binary],
            cwd=bundle,
            env=env,
            capture_output=True,
            input=b"qsnfj\n",
            timeout=20,
            check=False,
        )
        assert no_tty.returncode == 1
        report["checks"].append("Silent hidden gate, case/3 retries, help refusal, pipe refusal")
        forbidden = (".venv", "qrft/decoder", "qrft/control", "pyside6")
        for command in report["commands"]:
            for process in command["processes"]:
                for module in process.get("modules", []):
                    assert not any(s in module.lower().replace("\\", "/") for s in forbidden), (
                        module
                    )
                    assert Path(module).is_relative_to(bundle) or Path(module).is_relative_to(
                        Path(os.environ["SystemRoot"])
                    ), module
        report["checks"].append(
            "Observed loaded modules exclude project venv and forbidden subsystems"
        )
        assert not list(bundle.rglob("*.jsonl"))
        report.update(
            status="PASS",
            automatic_check_count=len(report["checks"]),
            temporary_archive_files=0,
            physical_screen_recording="NOT TESTED",
        )
    except BaseException as exc:
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        (root / "frozen-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def native(root, explicit_log):
    report = json.loads((root / "frozen-report.json").read_text(encoding="utf-8"))
    exe = Path(report["exe"])
    # More than 5 seconds of DATA, with enough parallel work to observe 3 workers.
    mode = "log" if explicit_log else "default"
    source = root / f"Native Folder 中文 {mode}"
    source.mkdir()
    (source / "binary.bin").write_bytes(random.Random(40).randbytes(2100 * 400))
    args = [exe, "play", source, "--workers", "3"]
    before = snapshot(exe.parent)
    if explicit_log:
        args.extend(["--log", root / "native-player.jsonl"])
    result = Terminal(args, exe.parent).finish(timeout=600)
    (root / f"native-{mode}-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert result["returncode"] == 0, result
    workers = [p for p in result["processes"] if "--multiprocessing-fork" in p["command"]]
    assert len(workers) == 3, workers
    assert all(Path(p["exe"]) == exe for p in workers)
    assert not any(psutil.pid_exists(p["pid"]) for p in workers)
    assert "DONE" in result["stdout"]
    progress = re.findall(
        r"\[(\d{2}:\d{2}:\d{2})\] DATA .*?elapsed (\d{2}:\d{2}:\d{2})", result["stdout"]
    )
    elapsed = [
        sum(int(p) * scale for p, scale in zip(value.split(":"), (3600, 60, 1)))
        for _, value in progress
    ]
    assert len(elapsed) >= 3 and all(4 <= b - a <= 6 for a, b in itertools.pairwise(elapsed[:-1]))
    if explicit_log:
        events = [
            json.loads(line) for line in (root / "native-player.jsonl").read_text().splitlines()
        ]
        display = [event for event in events if event["event"] == "display"]
        assert display[0]["packet_id"] == 88888888 and display[-1]["packet_id"] == 99999999
        assert [event["packet_id"] for event in display[1:-1]] == list(range(len(display) - 2))
        states = [event for event in events if event["event"] == "state"]
        assert [event["state"] for event in states] == ["PLAYING", "PAUSED", "PLAYING"]
        assert states[1]["position"] == states[2]["position"]
    assert snapshot(exe.parent) == before
    if not explicit_log:
        assert not (root / "native-player.jsonl").exists()
    assert not list(source.rglob("*.zip"))
    modules = [module for p in result["processes"] for module in p.get("modules", [])]
    assert any(Path(module).name.lower() == "python312.dll" for module in modules)
    assert any(Path(module).name.lower() == "cv2.pyd" for module in modules)
    assert all(
        Path(module).is_relative_to(exe.parent)
        or Path(module).is_relative_to(Path(os.environ["SystemRoot"]))
        for module in modules
    )
    result.update(
        status="PASS",
        worker_count=3,
        no_orphan_workers=True,
        progress_rows=len(progress),
        explicit_player_log=explicit_log,
    )
    (root / f"native-{mode}-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Native frozen player: 3 workers exited; console and resources recorded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--log", action="store_true")
    args = parser.parse_args()
    if args.native:
        native(args.root.resolve(), args.log)
    else:
        run(args.zip.resolve(), args.root)

"""Exercise the three frozen EXEs, including an actual binary/AVI/HTTP recovery chain."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    binaries = {
        name: (args.dist / name / f"{name}.exe").resolve()
        for name in ("QRFT-Encoder-CLI", "QRFT-Decoder", "QRFT-Control")
    }
    for binary in binaries.values():
        if not binary.is_file():
            raise FileNotFoundError(binary)
    with tempfile.TemporaryDirectory(prefix="qrft-exe-") as directory:
        root = Path(directory)
        env = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QRFT_API_TOKEN": "smoke-only-token",
            "QRFT_DB_PATH": str(root / "control.db"),
            "QRFT_OUTPUT_DIR": str(root / "recovered"),
        }

        def run(name, *options):
            if name == "QRFT-Encoder-CLI":
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
                from encoder_console_driver import run_encoder

                result = run_encoder(
                    [str(binaries[name]), *map(str, options)], env=env, cwd=root, timeout=60
                )
                if result.returncode:
                    raise RuntimeError(result.stdout)
                return
            subprocess.run(
                [str(binaries[name]), *map(str, options)], env=env, cwd=root, check=True, timeout=60
            )

        source = root / "中文文件.exe"
        payload = bytes(range(256)) + b"\x00\xff"
        source.write_bytes(payload)
        images = root / "png"
        run("QRFT-Encoder-CLI", "export", source, "--output", images, "--chunk-size", 64)
        run("QRFT-Decoder", "--workspace", root / "desktop", "--smoke-test")
        if not (root / "desktop" / ".qrft-decoder" / "control.sqlite3").is_file():
            raise RuntimeError("Decoder GUI did not start its managed control process")
        import cv2
        import numpy as np

        paths = [
            images / "00000000-start.png",
            *sorted(images.glob("*-data.png")),
            images / "99999999-finish.png",
        ]

        def load(path):
            return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

        height = width = 926
        video = root / "video.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 5, (width, height))
        if not writer.isOpened():
            raise OSError("Cannot create smoke AVI")
        try:
            for path in paths:
                qr = load(path)
                image = np.full((height, width, 3), 255, dtype=np.uint8)
                h, w = qr.shape[:2]
                y, x = (height - h) // 2, (width - w) // 2
                image[y : y + h, x : x + w] = qr
                for _ in range(30):
                    writer.write(image)
        finally:
            writer.release()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = subprocess.Popen(
            [str(binaries["QRFT-Control"]), "--port", str(port)],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"

        def api(route, body=None):
            request = urllib.request.Request(
                base + route,
                data=json.dumps(body).encode() if body is not None else None,
                headers={
                    "Authorization": "Bearer smoke-only-token",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)

        try:
            for attempt in range(100):
                try:
                    api("/health")
                    break
                except (OSError, urllib.error.URLError):
                    if server.poll() is not None:
                        raise RuntimeError("Control EXE exited during startup") from None
                    time.sleep(0.1)
            else:
                raise TimeoutError("Control startup timeout")
            task = api("/tasks", {"name": "Frozen EXE binary roundtrip"})["id"]
            api(
                "/videos",
                {"task_id": task, "path": str(video), "duration_seconds": len(paths) * 30 / 5},
            )
            config = root / "worker.json"
            config.write_text(
                json.dumps({"server": base, "node_id": "frozen-worker"}), encoding="utf-8"
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        run,
                        "QRFT-Decoder",
                        "worker",
                        "--config",
                        config,
                        "--node-id",
                        f"frozen-worker-{index}",
                        "--once",
                    )
                    for index in range(2)
                ]
                for future in futures:
                    future.result()
            slices = api("/slices")
            assert len(slices) == 2 and all(item["state"] == "done" for item in slices)
            assert len({item["owner"] for item in slices}) == 2
            restored = api(f"/tasks/{task}/recover", {})
            assert restored["status"] == "verified"
            assert Path(restored["path"]).read_bytes() == payload
            assert restored["sha256"] == hashlib.sha256(payload).hexdigest()
            print(
                "PASS: three EXEs; decoder GUI startup; CLI PNG -> AVI -> HTTP Worker -> SQLite -> MD5/SHA256"
            )
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == "__main__":
    main()

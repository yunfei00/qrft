"""Exercise all four frozen EXEs, including an actual binary/AVI/HTTP recovery chain."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
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
        for name in ("QRFT-Encoder-CLI", "QRFT-Encoder-GUI", "QRFT-Decoder", "QRFT-Control")
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
            subprocess.run(
                [str(binaries[name]), *map(str, options)], env=env, cwd=root, check=True, timeout=60
            )

        source = root / "中文文件.exe"
        payload = bytes(range(256)) + b"\x00\xff"
        source.write_bytes(payload)
        images = root / "png"
        run("QRFT-Encoder-CLI", "export", source, "--output", images, "--chunk-size", 64)
        run("QRFT-Encoder-GUI", "--smoke-test")
        run(
            "QRFT-Encoder-CLI",
            "play",
            source,
            "--interval-ms",
            10,
            "--initial-delay-ms",
            0,
            "--windowed",
            "--exit-when-finished",
        )
        import cv2
        import numpy as np

        paths = [
            images / "00000000-start.png",
            *sorted(images.glob("*-data.png")),
            images / "99999999-finish.png",
        ]

        def load(path):
            return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

        first = load(paths[0])
        height, width = first.shape[:2]
        video = root / "video.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 5, (width, height))
        if not writer.isOpened():
            raise OSError("Cannot create smoke AVI")
        try:
            for path in paths:
                image = cv2.resize(load(path), (width, height), interpolation=cv2.INTER_NEAREST)
                for _ in range(30):
                    writer.write(image)
        finally:
            writer.release()
        run("QRFT-Decoder", video, "--output", root / "local", "--sample-fps", 5)
        assert (root / "local" / source.name).read_bytes() == payload
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
                "PASS: four EXEs; Qt startup; CLI PNG -> AVI -> local decoder and HTTP Worker -> SQLite -> SHA256"
            )
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == "__main__":
    main()

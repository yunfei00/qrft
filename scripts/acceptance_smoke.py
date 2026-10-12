"""Copy the complete bundle to a clean directory and execute the frozen acceptance tool."""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil


def security_smoke(bundle, output):
    """实际 Control EXE：错误 Token/实例不得创建任何任务。"""
    with tempfile.TemporaryDirectory(prefix="qrft-control-isolation-") as directory:
        root = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        token = secrets.token_urlsafe(32)
        env = {
            **os.environ,
            "QRFT_API_TOKEN": token,
            "QRFT_ACCEPTANCE_ID": "owned-security-test",
            "QRFT_DB_PATH": str(root / "control.db"),
            "QRFT_OUTPUT_DIR": str(root / "out"),
        }
        process = subprocess.Popen(
            [str(bundle / "QRFT-Control" / "QRFT-Control.exe"), "--port", str(port)],
            env=env,
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(route, authorization, instance=None, body=None):
            headers = {
                "Authorization": f"Bearer {authorization}",
                "Content-Type": "application/json",
            }
            if instance is not None:
                headers["X-QRFT-Acceptance-ID"] = instance
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}" + route,
                headers=headers,
                data=json.dumps(body).encode() if body is not None else None,
            )
            with opener.open(req, timeout=5) as response:
                return json.load(response)

        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    health = request("/health", token)
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Isolation Control EXE exited") from None
                    time.sleep(0.1)
            else:
                raise TimeoutError("Isolation Control startup timeout")
            if health.get("acceptance_instance") != "owned-security-test":
                raise RuntimeError("Frozen Control does not expose correct acceptance identity")
            evidence = {}
            for name, secret, instance, expected in (
                ("wrong_token", "invalid-token", None, 401),
                ("wrong_instance", token, "other-session", 409),
            ):
                try:
                    request("/tasks", secret, instance, {"name": "must not mutate"})
                except urllib.error.HTTPError as exc:
                    if exc.code != expected:
                        raise RuntimeError(f"Unexpected isolation response: {exc.code}") from None
                    evidence[name] = exc.code
                else:
                    raise RuntimeError("Frozen Control accepted invalid token/instance")
            tasks = request("/tasks", token)
            if tasks:
                raise RuntimeError("Isolation requests changed task data")
            evidence.update(tasks_created=0, legacy_api_compatible=True)
            with (output / f"isolation-{secrets.token_hex(8)}.json").open(
                "x", encoding="utf-8"
            ) as stream:
                json.dump(evidence, stream, indent=2)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("acceptance-evidence"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous_reports = set(output.glob("*/report.json"))
    with tempfile.TemporaryDirectory(prefix="qrft-acceptance-clean-") as directory:
        bundle = Path(directory) / "中文程序目录"
        shutil.copytree(args.dist, bundle)
        binary = bundle / "QRFT-Acceptance" / "QRFT-Acceptance.exe"
        security_smoke(bundle, output)
        env = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "PATH": str(Path(os.environ["SystemRoot"]) / "System32")
            + os.pathsep
            + os.environ["SystemRoot"],
        }
        env.pop("PYTHONPATH", None)
        env.pop("VIRTUAL_ENV", None)
        for arguments, timeout in (
            (["--smoke-test"], 30),
            (["--headless", "--programs", str(bundle), "--output", str(output)], 300),
            (
                [
                    "--headless",
                    "--programs",
                    str(bundle),
                    "--output",
                    str(output),
                    "--items",
                    "environment",
                    "v2",
                ],
                120,
            ),
            (
                [
                    "--headless",
                    "--programs",
                    str(bundle),
                    "--output",
                    str(output),
                    "--items",
                    "qr_performance",
                ],
                60,
            ),
        ):
            process = subprocess.Popen([str(binary), *arguments], cwd=directory, env=env)
            try:
                code = process.wait(timeout=timeout)
            finally:
                if process.poll() is None:
                    children = psutil.Process(process.pid).children(recursive=True)
                    for child in children:
                        try:
                            child.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    process.terminate()
                    process.wait(timeout=10)
                    _, alive = psutil.wait_procs(children, timeout=5)
                    for child in alive:
                        child.kill()
            if code:
                reports = set(output.glob("*/report.json")) - previous_reports
                for report in reports:
                    data = json.loads(report.read_text(encoding="utf-8"))
                    print(json.dumps(data["results"], ensure_ascii=False, indent=2))
                raise RuntimeError(f"Acceptance EXE failed: {code}; evidence: {output}")
        reports = set(output.glob("*/report.json")) - previous_reports
        if not reports or not any(
            json.loads(p.read_text(encoding="utf-8"))["candidate_software_gate"] for p in reports
        ):
            raise RuntimeError("Missing or incomplete acceptance report")
        print(
            "PASS: actual Acceptance EXE Qt startup, four EXEs, dual Worker, retransmission, fault recovery"
        )


if __name__ == "__main__":
    main()

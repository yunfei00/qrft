"""Copy the complete bundle to a clean directory and execute the frozen acceptance tool."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("acceptance-evidence"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qrft-acceptance-clean-") as directory:
        bundle = Path(directory) / "中文程序目录"
        shutil.copytree(args.dist, bundle)
        binary = bundle / "QRFT-Acceptance" / "QRFT-Acceptance.exe"
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
                reports = list(output.glob("*/report.json"))
                for report in reports:
                    data = json.loads(report.read_text(encoding="utf-8"))
                    print(json.dumps(data["results"], ensure_ascii=False, indent=2))
                raise RuntimeError(f"Acceptance EXE failed: {code}; evidence: {output}")
        reports = list(output.glob("*/report.json"))
        if not reports or not all(
            json.loads(p.read_text(encoding="utf-8"))["candidate_software_gate"] for p in reports
        ):
            raise RuntimeError("Missing or incomplete acceptance report")
        print(
            "PASS: actual Acceptance EXE Qt startup, four EXEs, dual Worker, retransmission, fault recovery"
        )


if __name__ == "__main__":
    main()

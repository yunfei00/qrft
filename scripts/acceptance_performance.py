"""Repeatable bounded-memory acceptance benchmark; explicitly separates hashing and synthetic QR."""

import argparse
import json
from pathlib import Path

from qrft.acceptance.runner import Runner
from qrft.decoder.video import iter_video_frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--programs", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("temp/acceptance-performance"))
    parser.add_argument("--size-mb", type=int, choices=(10, 100, 1024), default=10)
    args = parser.parse_args()
    runner = Runner(
        args.programs, args.output, selected=["performance"], size_bytes=args.size_mb * 1024**2
    )
    report = runner.execute()
    if report["counts"]["failed"]:
        raise RuntimeError("Hash benchmark failed; inspect saved report")
    # This benchmark uses the actual CLI EXE for PNG, then actual ZXing core on synthetic AVI.
    import time

    runner.ensure_video()
    started = time.perf_counter()
    frames = sum(1 for _ in iter_video_frames(runner.video, sample_fps=5))
    seconds = time.perf_counter() - started
    result = {
        "scope": "synthetic AVI, real ZXing core; not recorded screen transfer",
        "decoded_frames": frames,
        "seconds": seconds,
        "frames_per_second": frames / seconds,
        "hash_report": str(runner.root / "report.json"),
    }
    runner.evidence("synthetic-zxing.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

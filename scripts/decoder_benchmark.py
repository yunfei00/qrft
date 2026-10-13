"""Reproducible real synthetic MP4 benchmark; generation can be reused fairly."""

import argparse
import json
import uuid
from pathlib import Path

from qrft.acceptance.benchmark import generate_fixture, scan_fixture
from qrft.acceptance.resources import ResourceBudget, environment, owned_directory, save_json


def run(directory: Path, size_kib: int, workers: int, *, reuse: Path | None = None) -> dict:
    owned_directory(directory)
    budget = ResourceBudget(directory)
    budget.check(force=True)
    fixture = (
        json.loads(reuse.read_text(encoding="utf-8"))
        if reuse
        else generate_fixture(directory / "fixture", size_kib, budget)
    )
    report = scan_fixture(directory / "scan", fixture, workers, budget=budget)
    report.update(
        environment(), media=fixture["media"], encoding_seconds=fixture["encoding_seconds"]
    )
    report["scope"] = "Synthetic MP4 + real ZXing/OpenCV, HTTP Workers, SQLite; not screen transfer"
    report["fixture_reused"] = reuse is not None
    save_json(directory / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-kib", type=int, default=16)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=2)
    parser.add_argument("--directory", type=Path)
    parser.add_argument(
        "--reuse-fixture", type=Path, help="Reuse a previously generated fixture.json"
    )
    args = parser.parse_args()
    if args.size_kib <= 0:
        parser.error("size-kib must be positive")
    directory = args.directory or Path("temp") / f"decoder-benchmark-{uuid.uuid4().hex}"
    print(
        json.dumps(
            run(directory, args.size_kib, args.workers, reuse=args.reuse_fixture),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

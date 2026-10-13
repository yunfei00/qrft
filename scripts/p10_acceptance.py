"""P10 owned, resource-limited real-source performance and stability acceptance."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from qrft.acceptance.benchmark import generate_fixture, scan_fixture, summarize
from qrft.acceptance.resources import ResourceBudget, ResourceLimit, environment, save_json


def matrix(
    root,
    budget,
    *,
    repeats=3,
    sizes=(64, 1024),
    workers=(1, 2, 4),
    include_large=False,
    render_processes=1,
):
    directory = root / (
        "matrix"
        if list(sizes) == [64, 1024]
        else "matrix-supplement-" + "-".join(str(size) for size in sizes)
    )
    directory.mkdir(exist_ok=False)
    report = {
        "environment": environment(),
        "scope": "synthetic MP4, not screen capture",
        "levels": [],
    }
    save_json(directory / "report.json", report)
    for size in sizes:
        if size > 1024:
            reference_path = root / (
                "matrix-supplement-1024/report.json"
                if render_processes > 1
                else "matrix/report.json"
            )
            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            medium = next(level for level in reference["levels"] if level["size_kib"] == 1024)
            ratio = ((size * 1024 + 1399) // 1400 + 40) / medium["fixture"]["media"]["frames"]
            predicted = (
                (
                    medium["fixture"]["encoding_seconds"]
                    + max(r["scan_seconds"] for r in medium["runs"])
                )
                * ratio
                * 1.3
            )
            report["preflight"] = {
                "estimated_seconds_with_margin": predicted,
                "estimated_video_bytes_with_margin": int(
                    medium["fixture"]["video_bytes"] * ratio * 1.3
                ),
            }
            save_json(directory / "report.json", report)
            if predicted > budget.item_seconds:
                raise ResourceLimit(
                    "BLOCKED_BY_LIMIT: supplemental video forecast exceeds item budget"
                )
            budget.check(
                reserve_bytes=report["preflight"]["estimated_video_bytes_with_margin"]
                + size * 1024 * 5,
                force=True,
            )
        fixture = generate_fixture(
            directory / f"fixture-{size}kib", size, budget, render_processes=render_processes
        )
        level = {"size_kib": size, "fixture": fixture, "runs": []}
        report["levels"].append(level)
        save_json(directory / "report.json", report)
        for repeat in range(repeats):
            # Rotate execution order to reduce order/warm-cache bias.
            order = list(workers[repeat % len(workers) :]) + list(workers[: repeat % len(workers)])
            for count in order:
                print(f"scan {size} KiB, workers={count}, repeat={repeat + 1}", flush=True)
                run_dir = directory / f"scan-{size}kib-w{count}-r{repeat + 1}"
                run = scan_fixture(
                    run_dir, fixture, count, budget=budget, interrupt_once=size >= 4096
                )
                run.update(repeat=repeat + 1, directory=str(run_dir.relative_to(root)))
                level["runs"].append(run)
                level["summary"] = summarize(level["runs"])
                save_json(directory / "report.json", report)
                print(f"PASS scan_seconds={run['scan_seconds']:.3f}", flush=True)
    medium = next((level for level in report["levels"] if level["size_kib"] == 1024), None)
    if medium:
        fixture = medium["fixture"]
        report["estimates"] = []
        for size in (10240, 51200, 102400, 1048576):
            packets = (size * 1024 + 1399) // 1400
            ratio = (packets + 40) / fixture["media"]["frames"]
            estimate = {
                "size_kib": size,
                "data_packets": packets,
                "qr_frames": packets + 40,
                "nominal_video_seconds": (packets + 40) / 20,
                "encoding_seconds_with_30pct_margin": fixture["encoding_seconds"] * ratio * 1.3,
                "scan_seconds_with_30pct_margin": max(r["scan_seconds"] for r in medium["runs"])
                * ratio
                * 1.3,
                "video_bytes_with_30pct_margin": int(fixture["video_bytes"] * ratio * 1.3),
                "status": "NOT RUN",
                "reason": "conditional larger video; requires budget check",
            }
            report["estimates"].append(estimate)
        if include_large:
            estimate = report["estimates"][0]
            predicted = (
                estimate["encoding_seconds_with_30pct_margin"]
                + estimate["scan_seconds_with_30pct_margin"]
            )
            remaining = budget.total_seconds - (time.monotonic() - budget.started)
            if predicted > budget.item_seconds or predicted > remaining - 2700:
                estimate["reason"] = (
                    "BLOCKED_BY_LIMIT: 30-minute item or remaining stability budget"
                )
            else:
                try:
                    budget.check(
                        reserve_bytes=estimate["video_bytes_with_30pct_margin"], force=True
                    )
                    large = generate_fixture(directory / "fixture-10240kib", 10240, budget)
                    run = scan_fixture(
                        directory / "scan-10240kib-w2-r1",
                        large,
                        2,
                        budget=budget,
                        interrupt_once=True,
                    )
                    report["levels"].append(
                        {
                            "size_kib": 10240,
                            "fixture": large,
                            "runs": [run],
                            "summary": summarize([run]),
                        }
                    )
                    estimate.update(status="PASS", reason="real full chain with pause/resume")
                except (ResourceLimit, TimeoutError) as exc:
                    estimate["reason"] = str(exc)
        for estimate in report["estimates"][1:]:
            estimate["reason"] = (
                "1 GiB QR/video prohibited by plan"
                if estimate["size_kib"] == 1048576
                else "conditional video exceeds measured per-item budget; use separate SQLite stress"
            )
    report["resources"] = budget.snapshot()
    report["status"] = "PASS"
    save_json(directory / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("matrix", "storage", "stability", "faults", "queries"))
    parser.add_argument("--root", type=Path, required=True, help="Existing owned P10 evidence root")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--sizes-kib", type=int, nargs="+", default=[64, 1024])
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--include-large", action="store_true")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--file-mib", type=int, default=100)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--render-processes", type=int, choices=range(1, 5), default=1)
    args = parser.parse_args()
    if (
        args.repeats < 1
        or any(size <= 0 for size in args.sizes_kib)
        or any(not 1 <= count <= 16 for count in args.workers)
        or args.file_mib <= 0
    ):
        parser.error("positive sizes/repeats and 1..16 Worker processes required")
    budget = ResourceBudget(args.root)
    budget.check(force=True)
    if not (args.root / "environment.json").exists():
        save_json(args.root / "environment.json", environment())
    try:
        if args.mode == "matrix":
            matrix(
                args.root,
                budget,
                repeats=args.repeats,
                sizes=args.sizes_kib,
                workers=tuple(args.workers),
                include_large=args.include_large,
                render_processes=args.render_processes,
            )
        elif args.mode == "storage":
            from qrft.acceptance.p10_storage import run

            run(args.root, budget, args.file_mib)
        elif args.mode == "queries":
            from qrft.acceptance.p10_storage import remeasure_queries

            remeasure_queries(args.root, args.file_mib)
        elif args.mode == "stability":
            from qrft.acceptance.p10_stability import run

            run(args.root, budget, args.fixture, args.seconds)
        else:
            from qrft.acceptance.p10_faults import run

            run(args.root, budget, args.fixture)
    except KeyboardInterrupt:
        save_json(
            args.root / f"{args.mode}-cancelled.json",
            {
                "status": "CANCELLED",
                "reason": "keyboard interrupt; owned subprocess cleanup requested",
            },
        )
        return 130
    except (ResourceLimit, TimeoutError) as exc:
        save_json(
            args.root / f"{args.mode}-blocked.json",
            {"status": "BLOCKED_BY_LIMIT", "reason": str(exc)},
        )
        return 2
    except Exception:
        save_json(
            args.root / f"{args.mode}-failure.json",
            {"status": "FAIL", "error": traceback.format_exc()},
        )
        raise
    finally:
        save_json(args.root / "resource-status.json", budget.snapshot())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

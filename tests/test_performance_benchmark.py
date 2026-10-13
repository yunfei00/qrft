import json
from types import SimpleNamespace

import pytest

from qrft.acceptance.benchmark import generate_fixture, hashes, scan_fixture, summarize
from qrft.acceptance.resources import GIB, ResourceBudget, ResourceLimit, owned_directory


def test_budget_protects_unknown_directories_and_low_free_disk(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="owned"):
        ResourceBudget(tmp_path)
    root = owned_directory(tmp_path / "owned")
    budget = ResourceBudget(root)
    monkeypatch.setattr(
        "qrft.acceptance.resources.psutil.disk_usage", lambda _: SimpleNamespace(free=7 * GIB)
    )
    with pytest.raises(ResourceLimit, match="free disk"):
        budget.check(force=True)
    assert (root / "OWNER.txt").is_file()


def test_budget_preserves_global_deadline_and_checks_memory(tmp_path):
    root = owned_directory(tmp_path / "owned")
    first = ResourceBudget(root, total_seconds=300)
    second = ResourceBudget(root, total_seconds=9999)
    assert second.total_seconds == first.total_seconds == 300
    with pytest.raises(ResourceLimit, match="memory"):
        second.check(rss=second.max_rss_bytes + 1)
    second.started -= 301
    with pytest.raises(ResourceLimit, match="elapsed"):
        second.check()


def test_video_generation_obeys_guard_and_releases_partial_video(tmp_path):
    class StopAfterFirstFrames:
        frames = 0

        def check(self, **options):
            if "rss" in options:
                self.frames += 1
                if self.frames == 2:
                    raise ResourceLimit("controlled disk-space warning")

    with pytest.raises(ResourceLimit, match="disk-space"):
        generate_fixture(tmp_path / "fixture", 1, StopAfterFirstFrames())
    # Failure evidence remains owned by the test and is never reported as PASS.
    assert (tmp_path / "fixture" / "synthetic.mp4").stat().st_size > 0
    assert not (tmp_path / "fixture" / "fixture.json").exists()


def test_one_gib_video_is_forbidden_before_creating_source_or_video(tmp_path):
    with pytest.raises(ResourceLimit, match="forbids"):
        generate_fixture(tmp_path / "forbidden", 1024 * 1024)
    assert not (tmp_path / "forbidden").exists()


def test_same_actual_mp4_is_reused_by_one_and_two_worker_processes(tmp_path):
    fixture = generate_fixture(tmp_path / "fixture", 8)
    original_video_hash = hashes(tmp_path / "fixture" / "synthetic.mp4")
    reports = [scan_fixture(tmp_path / f"workers-{count}", fixture, count) for count in (1, 2)]
    assert hashes(tmp_path / "fixture" / "synthetic.mp4") == original_video_hash
    for report in reports:
        assert report["bytes_equal"] and report["reopened_persistent_result"]
        assert report["missing_count"] == report["conflicts"] == 0
        assert len(report["nodes_with_completed_slices"]) == report["workers"]
        assert report["hashes"] == fixture["hashes"]
        assert (
            json.loads((tmp_path / f"workers-{report['workers']}" / "report.json").read_text())[
                "status"
            ]
            == "PASS"
        )


def test_benchmark_summary_retains_multicore_slowdowns():
    runs = [
        {
            "workers": count,
            "scan_seconds": seconds,
            "effective_packets_per_second": 100 / seconds,
            "resources": {
                "rss_peak_bytes": count * 100,
                "cpu_peak_percent": count * 80,
                "process_io_read_bytes": 20,
                "process_io_write_bytes": 10,
            },
        }
        for count, seconds in ((1, 2), (1, 3), (1, 4), (2, 6), (2, 8), (2, 7))
    ]
    summary = summarize(runs)
    assert summary[0]["scan_median_seconds"] == 3
    assert summary[1]["scan_median_seconds"] == 7
    assert summary[1]["speedup_vs_one_worker"] == 3 / 7
    assert summary[1]["scan_min_seconds"] == 6 and summary[1]["scan_max_seconds"] == 8


def test_actual_v2_sqlite_stress_reopens_recovers_and_protects_outputs(tmp_path):
    from qrft.acceptance.p10_storage import run

    root = owned_directory(tmp_path / "owned-storage")
    report = run(root, ResourceBudget(root), file_mib=1)
    assert report["status"] == "PASS" and report["bytes_equal"]
    assert report["recovered_after_database_reopen"]
    assert report["incomplete_not_published"] and report["unwritable_output_rejected"]
    assert report["existing_file_protected"]
    assert report["missing_export"]["count"] > 0
    assert report["quarantined_conflict_count"] == 1
    assert report["stored_packets"] == 749
    assert all(
        q["median_seconds"] > 0 and q["timer_api"] == "perf_counter"
        for q in report["queries"].values()
    )


def test_bounded_parallel_renderer_preserves_actual_mp4_pixels_and_payload(tmp_path):
    import cv2
    import numpy as np

    fixtures = [
        generate_fixture(tmp_path / f"render-{count}", 8, render_processes=count)
        for count in (1, 2)
    ]
    assert fixtures[0]["hashes"] == fixtures[1]["hashes"]
    assert fixtures[1]["maximum_pending_render_frames"] <= 4
    captures = [cv2.VideoCapture(f["video"]) for f in fixtures]
    try:
        for _ in range(fixtures[0]["media"]["frames"]):
            frames = [capture.read() for capture in captures]
            assert all(ok for ok, _ in frames)
            assert np.array_equal(frames[0][1], frames[1][1])
    finally:
        for capture in captures:
            capture.release()


def test_public_report_masks_tokens_and_absolute_paths(tmp_path):
    from qrft.acceptance.p10_report import sanitize

    value = {
        "token": "private",
        "lease_token": "lease",
        "path": str(tmp_path / "sample.mp4"),
        "other_path": "C:\\Users\\someone\\private.mp4",
        "md5": "ABC",
    }
    report = sanitize(value, tmp_path)
    assert report["token"] == report["lease_token"] == "[REDACTED]"
    assert report["path"].startswith("temp/")
    assert "someone" not in report["other_path"]
    assert report["md5"] == "ABC"

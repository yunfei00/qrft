"""Owned evidence directories, bounded workloads and process-tree measurements."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

import psutil

GIB = 1024**3
OWNER = "QRFT P10 isolated acceptance; retain evidence; created by current task"


class ResourceLimit(RuntimeError):
    """A measured resource or time budget was reached, never a passing result."""


def owned_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=False)
    (path / "OWNER.txt").write_text(OWNER + "\n", encoding="utf-8")
    return path


def save_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def environment() -> dict:
    def git(*args):
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "logical_cpus": psutil.cpu_count(),
        "memory_total_bytes": psutil.virtual_memory().total,
        "git_commit": git("rev-parse", "HEAD"),
        "git_worktree_dirty": bool(git("status", "--porcelain")),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("qrcode", "pillow", "opencv-python", "zxing-cpp", "PySide6", "psutil")
        },
    }


class ResourceBudget:
    def __init__(self, root: Path, *, total_seconds=7200, item_seconds=1800):
        if root.is_symlink():
            raise ValueError("P10 evidence root cannot be a symbolic link")
        self.root = root.resolve()
        marker = self.root / "OWNER.txt"
        if self.root.is_symlink() or not marker.is_file():
            raise ValueError("P10 requires an owned independent evidence directory")
        if marker.read_text(encoding="utf-8-sig").strip() != OWNER:
            raise ValueError("P10 evidence ownership mismatch")
        policy_path = self.root / "resource-policy.json"
        if policy_path.exists():
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        else:
            policy = {
                "started_at_epoch": time.time(),
                "total_seconds": total_seconds,
                "item_seconds": item_seconds,
                "initial_free_bytes": psutil.disk_usage(str(root)).free,
            }
            save_json(policy_path, policy)
        self.started = time.monotonic() - max(0, time.time() - policy["started_at_epoch"])
        self.total_seconds = policy["total_seconds"]
        self.item_seconds = policy["item_seconds"]
        self.initial_free = policy["initial_free_bytes"]
        self.free_floor = max(8 * GIB, int(self.initial_free * 0.2))
        self.max_created_bytes = 15 * GIB
        self.max_rss_bytes = min(8 * GIB, int(psutil.virtual_memory().total * 0.65))
        self.last_check = 0.0
        self.created_bytes = 0
        self.minimum_observed_free = self.initial_free

    def check(self, *, item_started=None, rss=0, reserve_bytes=0, force=False):
        now = time.monotonic()
        if now - self.started > self.total_seconds:
            raise ResourceLimit("BLOCKED_BY_LIMIT: total elapsed time budget")
        if item_started is not None and now - item_started > self.item_seconds:
            raise ResourceLimit("BLOCKED_BY_LIMIT: workload elapsed time budget")
        if rss > self.max_rss_bytes or psutil.virtual_memory().available < 512 * 1024**2:
            raise ResourceLimit("BLOCKED_BY_LIMIT: memory protection")
        if not force and not reserve_bytes and now - self.last_check < 5:
            return
        self.last_check = now
        free = psutil.disk_usage(str(self.root)).free
        self.minimum_observed_free = min(free, self.minimum_observed_free)
        # Only inspect owned files. No cleanup, permission changes or user files.
        self.created_bytes = 0
        for path in self.root.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    self.created_bytes += path.stat().st_size
            except FileNotFoundError:
                pass  # Owned temporary staging files may disappear during sampling.
        if free - reserve_bytes < self.free_floor:
            raise ResourceLimit("BLOCKED_BY_LIMIT: free disk floor")
        if self.created_bytes + reserve_bytes > self.max_created_bytes:
            raise ResourceLimit("BLOCKED_BY_LIMIT: 15 GiB evidence size cap")

    def snapshot(self):
        return {
            "initial_free_bytes": self.initial_free,
            "free_floor_bytes": self.free_floor,
            "minimum_observed_free_bytes": self.minimum_observed_free,
            "maximum_created_bytes": self.max_created_bytes,
            "created_bytes": self.created_bytes,
            "maximum_rss_bytes": self.max_rss_bytes,
            "elapsed_seconds": time.monotonic() - self.started,
            "total_budget_seconds": self.total_seconds,
            "item_budget_seconds": self.item_seconds,
        }


class ProcessSampler:
    """Bounded summary with identity checks, exited-process I/O retained."""

    def __init__(self, path: Path | None = None):
        self.rows = path.open("x", encoding="utf-8") if path else None
        self.processes = {}
        self.io = {}
        self.read_bytes = self.write_bytes = 0
        self.rss_start = None
        self.rss_last = self.rss_peak = self.cpu_peak = self.cpu_sum = self.samples = 0
        self.started = time.monotonic()
        self.last_sample = 0.0

    def sample(self, roots, *, force=False):
        now = time.monotonic()
        if not force and now - self.last_sample < 0.25:
            return self.rss_last
        self.last_sample = now
        alive = {}
        for root in roots:
            try:
                parent = psutil.Process(root.pid if hasattr(root, "pid") else root)
                for child in [parent, *parent.children(recursive=True)]:
                    alive[(child.pid, child.create_time())] = child
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        rss = cpu = 0
        for key, child in alive.items():
            try:
                process = self.processes.setdefault(key, child)
                rss += process.memory_info().rss
                cpu += process.cpu_percent()
                counters = process.io_counters()
                old = self.io.get(key, (counters.read_bytes, counters.write_bytes))
                self.read_bytes += max(0, counters.read_bytes - old[0])
                self.write_bytes += max(0, counters.write_bytes - old[1])
                self.io[key] = (counters.read_bytes, counters.write_bytes)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self.rss_start = rss if self.rss_start is None else self.rss_start
        self.rss_last = rss
        self.rss_peak = max(self.rss_peak, rss)
        self.cpu_peak = max(self.cpu_peak, cpu)
        self.cpu_sum += cpu
        self.samples += 1
        if self.rows:
            self.rows.write(
                json.dumps(
                    {"seconds": now - self.started, "rss": rss, "cpu": cpu, "active": len(alive)}
                )
                + "\n"
            )
            self.rows.flush()
        return rss

    def summary(self):
        return {
            "samples": self.samples,
            "rss_start_bytes": self.rss_start,
            "rss_peak_bytes": self.rss_peak,
            "rss_last_bytes": self.rss_last,
            "cpu_average_percent": self.cpu_sum / max(1, self.samples),
            "cpu_peak_percent": self.cpu_peak,
            "process_io_read_bytes": self.read_bytes,
            "process_io_write_bytes": self.write_bytes,
            "process_identities_seen": len(self.processes),
            "sampling_minimum_seconds": 0.25,
            "scope": "sum of observed process trees; CPU single-core percentages are summed; I/O excludes activity before discovery",
        }

    def close(self):
        if self.rows:
            self.rows.close()


def own_process():
    return psutil.Process(os.getpid())


class BackgroundMonitor:
    """Observe native allocations while a synchronous core operation is executing."""

    def __init__(self, sampler, budget, item_started):
        self.sampler, self.budget, self.item_started = sampler, budget, item_started
        self.stop = threading.Event()
        self.errors = []
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stop.is_set():
            try:
                rss = self.sampler.sample([own_process()])
                self.budget.check(item_started=self.item_started, rss=rss)
            except (ResourceLimit, OSError, ValueError) as exc:
                self.errors.append(exc)
                return
            self.stop.wait(0.25)

    def check(self):
        if self.errors:
            raise self.errors[0]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)
        self.check()

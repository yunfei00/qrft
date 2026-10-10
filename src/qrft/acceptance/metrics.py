"""psutil 原生进程指标；采样包括验收器和它直接创建的 EXE。"""

import os
import threading
import time

import psutil


class Monitor:
    def __init__(self, children):
        self.children = children
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.peak = 0
        self.counters = {}
        self.initial = {}
        self.initial_pids = {os.getpid(), *(p.pid for p in children if p.poll() is None)}
        self.started = time.monotonic()

    def __enter__(self):
        self.thread.start()
        return self

    def sample(self):
        while not self.stop.is_set():
            rss = 0
            for pid in {os.getpid(), *(p.pid for p in list(self.children) if p.poll() is None)}:
                try:
                    process = psutil.Process(pid)
                    cpu, io = process.cpu_times(), process.io_counters()
                    values = (cpu.user + cpu.system, io.read_bytes, io.write_bytes)
                    self.initial.setdefault(pid, values if pid in self.initial_pids else (0, 0, 0))
                    self.counters[pid] = values
                    rss += process.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            self.peak = max(self.peak, rss)
            self.stop.wait(0.2)

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=2)

    def result(self):
        totals = [
            sum(max(0, values[i] - self.initial[pid][i]) for pid, values in self.counters.items())
            for i in range(3)
        ]
        return {
            "sampled_peak_rss_bytes": self.peak,
            "cpu_seconds": totals[0],
            "cpu_percent_one_core": totals[0] / max(time.monotonic() - self.started, 0.001) * 100,
            "disk_read_bytes": totals[1],
            "disk_write_bytes": totals[2],
            "resource_scope": "验收器与自有 EXE；200ms 采样，短峰值可能漏采；CPU 可超过100%",
        }

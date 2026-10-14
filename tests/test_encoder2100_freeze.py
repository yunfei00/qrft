"""The frozen child must dispatch before any interactive CLI execution."""

import multiprocessing
import runpy
from pathlib import Path

import pytest

from qrft.encoder2100 import cli

ENTRY = Path(__file__).resolve().parents[1] / "src/qrft/encoder2100/entrypoint.py"


def test_frozen_console_dispatch_order(monkeypatch):
    events = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: events.append("freeze"))

    def main():
        events.append("gate")
        return 7

    monkeypatch.setattr(cli, "main", main)
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(ENTRY), run_name="__main__")
    assert exited.value.code == 7 and events == ["freeze", "gate"]


def test_frozen_worker_never_reenters_gate(monkeypatch):
    def worker_dispatch():
        raise SystemExit(0)

    monkeypatch.setattr(multiprocessing, "freeze_support", worker_dispatch)
    monkeypatch.setattr(cli, "main", lambda: pytest.fail("worker re-entered interactive gate"))
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(ENTRY), run_name="__main__")
    assert exited.value.code == 0

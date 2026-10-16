"""Packaged decoder opens the desktop and dispatches managed subprocesses."""

from qrft.decoder import entrypoint


def test_worker_dispatch(monkeypatch):
    observed = []
    monkeypatch.setattr(entrypoint, "worker_main", lambda args: observed.append(args) or 0)
    assert entrypoint.main(["worker", "--help"]) == 0
    assert observed == [["--help"]]


def test_default_gui_dispatch(monkeypatch):
    observed = []
    monkeypatch.setattr(entrypoint, "gui_main", lambda args: observed.append(args) or 0)
    assert entrypoint.main([]) == 0
    assert entrypoint.main(["--workspace", "task"]) == 0
    assert observed == [[], ["--workspace", "task"]]


def test_control_dispatch(monkeypatch):
    observed = []
    monkeypatch.setattr(entrypoint, "control_main", lambda args: observed.append(args) or 0)
    assert entrypoint.main(["control", "--port", "8787"]) == 0
    assert observed == [["--port", "8787"]]

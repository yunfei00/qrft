"""Packaged decoder exposes local recovery and worker commands."""

from qrft.decoder import entrypoint


def test_worker_dispatch(monkeypatch):
    observed = []
    monkeypatch.setattr(entrypoint, "worker_main", lambda args: observed.append(args) or 0)
    assert entrypoint.main(["worker", "--help"]) == 0
    assert observed == [["--help"]]


def test_local_dispatch(monkeypatch):
    observed = []
    monkeypatch.setattr(entrypoint, "local_main", lambda args: observed.append(args) or 0)
    assert entrypoint.main(["recording.avi", "--output", "result"]) == 0
    assert observed == [["recording.avi", "--output", "result"]]

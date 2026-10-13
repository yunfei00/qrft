"""Actual process crashes and HTTP failures on the medium synthetic video."""

from __future__ import annotations

import json
import time
from pathlib import Path

import psutil

from qrft.acceptance.benchmark import byte_equal
from qrft.acceptance.resources import ProcessSampler, environment, save_json
from qrft.decoder_gui.acceptance import FaultProxy
from qrft.decoder_gui.service import ManagedSession, inspect_video


def kill_owned_tree(process):
    """Only terminate the subprocess explicitly passed by its owner."""
    if process.poll() is not None:
        return []
    parent = psutil.Process(process.pid)
    children = parent.children(recursive=True)
    identities = [(p.pid, p.create_time()) for p in [*children, parent]]
    for child in [*reversed(children), parent]:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs([*children, parent], timeout=5)
    process.wait(timeout=5)
    return identities


def run(root, budget, fixture_path):
    if fixture_path is None:
        raise ValueError("--fixture requires the real medium fixture.json")
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    directory = root / "faults"
    directory.mkdir(exist_ok=False)
    started = time.monotonic()
    sampler = ProcessSampler(directory / "resources.jsonl")
    session = ManagedSession(directory / "workspace")
    proxy = None
    report = {
        "environment": environment(),
        "scope": "real local HTTP and OS-process faults, not physical network",
        "cases": [],
    }

    def wait(operation, predicate, seconds=240):
        deadline = time.monotonic() + seconds
        value = None
        while time.monotonic() < deadline:
            rss = sampler.sample([session.control, *session.workers])
            budget.check(item_started=started, rss=rss)
            value = operation()
            if predicate(value):
                return value
            time.sleep(0.2)
        raise TimeoutError(f"fault verification timed out: {value}")

    def register(name):
        task = session.client.request("/tasks", {"name": name, "protocol_version": 2})["id"]
        session.client.request(
            "/videos",
            {
                "task_id": task,
                "path": fixture["video"],
                "duration_seconds": fixture["media"]["duration_seconds"],
                "slice_seconds": 30,
            },
        )
        return task

    def active_checkpoint(task):
        videos = session.client.request(f"/videos?task_id={task}")
        return [
            s
            for video in videos
            for s in session.client.request(f"/slices?video_id={video['id']}")
            if s["state"] == "leased" and s["checkpoint_ms"] > s["start_ms"]
        ]

    def complete(task):
        return wait(
            lambda: session.client.request(f"/tasks/{task}/progress"),
            lambda p: p["slices"] and all(s["state"] == "done" for s in p["slices"]),
        )

    def recover(task):
        result = session.client.request(f"/tasks/{task}/recover", {})
        assert result["status"] == "verified" and result["md5"] == fixture["hashes"]["md5"]
        assert result["sha256"] == fixture["hashes"]["sha256"]
        assert byte_equal(Path(fixture["source"]), Path(result["path"]))
        return {k: v for k, v in result.items() if k != "path"}

    try:
        task = register("HTTP retry and killed Worker checkpoint takeover")
        upstream = session.client.server
        proxy = FaultProxy(upstream, session.token)
        session.client.server = proxy.url
        session.start(task, 2)
        lease = wait(lambda: active_checkpoint(task), bool)[0]
        stored_before = session.client.request(f"/tasks/{task}/progress")["stored"]
        victim = next(p for p in session.workers if lease["owner"] in p.args)
        killed = kill_owned_tree(victim)
        progress = complete(task)
        slices = session.client.request("/slices")
        reassigned = next(s for s in slices if s["id"] == lease["id"])
        assert reassigned["attempts"] >= 2 and reassigned["owner"] != lease["owner"]
        try:
            session.client.request(
                f"/slices/{lease['id']}/complete",
                {"node_id": lease["owner"], "lease_token": lease["lease_token"]},
            )
        except RuntimeError as exc:
            assert "409" in str(exc)
        else:
            raise AssertionError("stale lease accepted")
        assert any(e.get("status") == 503 for e in proxy.events)
        assert any(e["route"].endswith("/renew") and e.get("status") == 200 for e in proxy.events)
        assert progress["stored"] >= stored_before and progress["conflicts"] == 0
        report["cases"].append(
            {
                "name": "HTTP 503, renewal, actual Worker kill, checkpoint takeover, stale fencing",
                "status": "PASS",
                "stored_before": stored_before,
                "checkpoint_before_kill": lease["checkpoint_ms"],
                "reassigned": reassigned,
                "killed_processes": killed,
                "recovery": recover(task),
                "http_faults": sum(e.get("status") == 503 for e in proxy.events),
                "renewals": sum(
                    e["route"].endswith("/renew") and e.get("status") == 200 for e in proxy.events
                ),
            }
        )
        session.pause(task)
        session.client.server = upstream
        proxy.close()
        proxy = None
        task = register("abrupt Control crash and persistent reconnect")
        session.start(task, 2)
        leases = wait(lambda: active_checkpoint(task), bool)
        before = session.client.request(f"/tasks/{task}/progress")["stored"]
        killed = kill_owned_tree(session.control)
        session.close()
        session = ManagedSession(directory / "workspace")
        assert session.client.request(f"/tasks/{task}/progress")["stored"] >= before
        session.start(task, 2)
        progress = complete(task)
        assert progress["stored"] >= before and progress["conflicts"] == 0
        report["cases"].append(
            {
                "name": "abrupt Control crash / new authenticated Control / persisted packets and checkpoints",
                "status": "PASS",
                "stored_before": before,
                "checkpoint_before_crash": leases,
                "killed_processes": killed,
                "recovery": recover(task),
            }
        )
        session.pause(task)
        assert session.client.request(f"/tasks/{task}/progress")["paused"]
        for video in session.client.request(f"/videos?task_id={task}"):
            session.client.request(f"/videos/{video['id']}/rescan", {})
        session.start(task, 2)
        videos = session.client.request(f"/videos?task_id={task}")
        wait(
            lambda: [
                s
                for video in videos
                for s in session.client.request(f"/slices?video_id={video['id']}")
            ],
            lambda slices: any(s["state"] == "leased" for s in slices),
        )
        session.cancel(task)
        assert session.client.request(f"/tasks/{task}/progress")["cancelled"]
        session.start(task, 2)
        assert not session.client.request(f"/tasks/{task}/progress")["cancelled"]
        complete(task)
        session.pause(task)
        report["cases"].append(
            {
                "name": "Pause/Resume and Cancel/Resume keep verified packets",
                "status": "PASS",
                "stored": session.client.request(f"/tasks/{task}/progress")["stored"],
            }
        )
        corrupt = directory / "truncated.mp4"
        with Path(fixture["video"]).open("rb") as source, corrupt.open("xb") as target:
            target.write(source.read(1024))
        try:
            inspect_video(corrupt)
        except OSError:
            pass
        else:
            raise AssertionError("truncated MP4 accepted")
        report["cases"].append({"name": "real truncated MP4 rejected", "status": "PASS"})
        report.update(
            status="PASS", total_seconds=time.monotonic() - started, resources=sampler.summary()
        )
        save_json(directory / "report.json", report)
        return report
    finally:
        session.close()
        if proxy:
            proxy.close()
        sampler.close()

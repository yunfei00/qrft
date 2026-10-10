"""时间片生成、超时重领、归属校验和完成幂等。"""

from __future__ import annotations

import sqlite3

from qrft.control.scheduler import add_slices, claim, complete, init_schema


def test_slice_coverage_and_idempotent_registration() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_schema(db)
    assert add_slices(db, 1, 65, slice_ms=30000, overlap_ms=1000) == 3
    assert add_slices(db, 1, 65, slice_ms=30000, overlap_ms=1000) == 3
    rows = db.execute("SELECT start_ms,end_ms FROM slices ORDER BY id").fetchall()
    assert [tuple(row) for row in rows] == [(0, 30000), (29000, 59000), (58000, 65000)]


def test_claim_lease_and_completion(tmp_path) -> None:
    db = sqlite3.connect(tmp_path / "leases.db")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE videos(id INTEGER PRIMARY KEY, path TEXT, task_id INTEGER)")
    db.execute("INSERT INTO videos VALUES (1, 'share/video.avi', 1)")
    init_schema(db)
    add_slices(db, 1, 2)
    db.commit()
    first = claim(db, "node-a", 10)
    assert first is not None
    assert first["path"] == "share/video.avi"
    assert claim(db, "node-b", 10) is None
    assert complete(db, first["id"], "node-b") == "lease_invalid"
    db.execute("UPDATE slices SET lease_until=0 WHERE id=?", (first["id"],))
    db.commit()
    second = claim(db, "node-b", 10)
    assert second is not None
    assert second["id"] == first["id"]
    assert second["attempts"] == 1
    assert complete(db, first["id"], "node-a") == "lease_invalid"
    assert complete(db, first["id"], "node-b") == "done"
    assert complete(db, first["id"], "node-b") == "already_done"
    assert claim(db, "node-c") is None

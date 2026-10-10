"""二维码原始包校验、去重、冲突隔离及租约续期。"""

from __future__ import annotations

import sqlite3

import pytest

from qrft.control.packets import ingest, init_schema
from qrft.control.scheduler import add_slices, claim, complete, renew
from qrft.control.scheduler import init_schema as init_slices
from qrft.core.protocol import ProtocolError, encode_data


def test_packet_ingest_and_conflict() -> None:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_schema(db)
    raw = encode_data(0, b"hello")
    assert ingest(db, 1, raw) == "inserted"
    assert ingest(db, 1, raw) == "duplicate"
    assert ingest(db, 1, encode_data(0, b"other")) == "conflict"
    assert db.execute("SELECT COUNT(*) FROM packets").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM packet_conflicts").fetchone()[0] == 1
    with pytest.raises(ProtocolError):
        ingest(db, 1, raw[:-1] + b"X")


def test_renew_owner_and_expiration(tmp_path) -> None:
    db = sqlite3.connect(tmp_path / "renew.db")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE videos(id INTEGER PRIMARY KEY, path TEXT)")
    db.execute("INSERT INTO videos VALUES (1, 'share.avi')")
    init_slices(db)
    add_slices(db, 1, 2)
    db.commit()
    lease = claim(db, "node-a", 10)
    assert lease is not None
    assert renew(db, lease["id"], "node-b", 10) == "lease_invalid"
    assert renew(db, lease["id"], "node-a", 10) == "renewed"
    assert complete(db, lease["id"], "node-a") == "done"
    assert renew(db, lease["id"], "node-a", 10) == "lease_invalid"

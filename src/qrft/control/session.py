"""Shared durable START binding for local video imports and Control."""

from qrft.control.packets import lock_protocol
from qrft.core.protocol import ProtocolError, decode_frame
from qrft.core.validation import validate_data, validate_manifest


def init_session(db):
    db.execute("CREATE TABLE IF NOT EXISTS task_finishes (task_id INTEGER PRIMARY KEY)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS task_manifests (task_id INTEGER PRIMARY KEY, "
        "start_frame BLOB NOT NULL,total_packets INTEGER NOT NULL, "
        "chunk_size INTEGER NOT NULL,file_size INTEGER NOT NULL)"
    )


def bind_start(db, task_id, raw):
    frame = decode_frame(raw)
    if frame.kind != "start" or frame.metadata is None:
        raise ProtocolError("START frame required")
    meta = frame.metadata
    if meta.get("version", 2) != frame.version:
        raise ProtocolError("START metadata version disagrees with wire protocol")
    validate_manifest(meta)
    lock_protocol(db, task_id, frame.version)
    old = db.execute(
        "SELECT start_frame FROM task_manifests WHERE task_id=?", (task_id,)
    ).fetchone()
    if old is not None:
        if decode_frame(bytes(old[0])).metadata != meta:
            raise ProtocolError("Conflicting START manifest")
        return "already_bound"
    for row in db.execute("SELECT frame FROM packets WHERE task_id=?", (task_id,)):
        try:
            validate_data(meta, decode_frame(bytes(row[0])))
        except ProtocolError as exc:
            raise ProtocolError("Stored DATA does not match START") from exc
    db.execute(
        "INSERT INTO task_manifests VALUES (?,?,?,?,?)",
        (
            task_id,
            raw,
            meta["total_packets"],
            meta["chunk_size"],
            -1,
        ),
    )
    return "bound"

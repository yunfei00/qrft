"""Durable single-task project, source-aware deduplication and verified publication."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
import zlib
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile

from qrft.encoder2100.archive import reject_link
from qrft.encoder2100.protocol import FINISH_ID, START_ID

from .folder import verify_folder
from .protocol import identity, parse, valid_data
from .video import fingerprint, frames

OWNER = "QRFT single decoder project v1\n"
EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".m4v",
    ".wmv",
    ".webm",
    ".mpg",
    ".mpeg",
    ".mts",
    ".m2ts",
}


def now():
    return datetime.now(UTC).isoformat()


def safe_directory(path):
    if path.exists() or path.is_symlink():
        reject_link(path, path.lstat())
        if not path.is_dir():
            raise ValueError("Project internal path must be a directory")
    else:
        path.mkdir()


class Project:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        reject_link(self.root, self.root.lstat())
        self.db = self.lock = self.handler = None
        self.logger = logging.getLogger(f"qrft.single.{uuid.uuid4().hex}")
        self.logger.propagate = False
        try:
            for part in ("videos", "state", "reports", "output"):
                safe_directory(self.root / part)
            state = self.root / "state"
            marker = state / "OWNER.txt"
            if marker.exists():
                reject_link(marker, marker.lstat())
                if marker.read_text(encoding="utf-8") != OWNER:
                    raise ValueError("Unrelated project state directory")
            else:
                if any(state.iterdir()) or any((self.root / "reports").iterdir()):
                    raise ValueError("Refusing to overwrite unrelated project state/reports")
                with marker.open("x", encoding="utf-8") as stream:
                    stream.write(OWNER)
            for name in (
                "project.db",
                "project.db-wal",
                "project.db-shm",
                "run.lock",
                "decode.log",
            ):
                path = state / name
                if path.exists() or path.is_symlink():
                    reject_link(path, path.lstat())
            self.lock = (state / "run.lock").open("a+b")
            if not self.lock.seek(0, 2):
                self.lock.write(b"0")
                self.lock.flush()
            self.lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise OSError("Project is already being decoded by another process") from None
            self.db = sqlite3.connect(state / "project.db")
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA cache_size=-4096")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 2):
                raise ValueError("Unsupported project database version")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS videos(
                    id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL,
                    size INTEGER, mtime_ns INTEGER, sha256 TEXT, active INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending', processed_frames INTEGER DEFAULT 0,
                    total_frames INTEGER, valid_frames INTEGER DEFAULT 0,
                    invalid_frames INTEGER DEFAULT 0, started TEXT, ended TEXT, error TEXT,
                    attempts INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS packets(
                    packet_id INTEGER NOT NULL,digest TEXT NOT NULL,content_md5 TEXT NOT NULL,
                    payload BLOB NOT NULL, PRIMARY KEY(packet_id,digest));
                CREATE TABLE IF NOT EXISTS receipts(
                    video_id INTEGER NOT NULL REFERENCES videos(id),packet_id INTEGER NOT NULL,
                    digest TEXT NOT NULL,first_seen TEXT NOT NULL,
                    PRIMARY KEY(video_id,packet_id,digest),
                    FOREIGN KEY(packet_id,digest) REFERENCES packets(packet_id,digest));
                CREATE INDEX IF NOT EXISTS receipts_packet ON receipts(packet_id,digest);
                CREATE VIEW IF NOT EXISTS observations AS SELECT r.video_id,p.packet_id,p.digest,
                    p.content_md5,p.payload,r.first_seen FROM receipts r JOIN packets p
                    ON r.packet_id=p.packet_id AND r.digest=p.digest;
                CREATE TABLE IF NOT EXISTS task(id INTEGER PRIMARY KEY CHECK(id=1), metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outputs(name TEXT PRIMARY KEY, size INTEGER, md5 TEXT, sha256 TEXT);
                PRAGMA user_version=2;
            """)
            self.handler = logging.FileHandler(state / "decode.log", encoding="utf-8")
            self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(self.handler)
            self.logger.setLevel(logging.INFO)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.handler is not None:
            self.logger.removeHandler(self.handler)
            self.handler.close()
            self.handler = None
        if self.lock is not None:
            self.lock.close()  # OS also releases the lock after a process crash.
            self.lock = None

    def discover(self):
        found = []
        for path in self.root.iterdir():
            if path.suffix.lower() in EXTENSIONS:
                reject_link(path, path.lstat())
                if path.is_file():
                    found.append(path)
        pending = [self.root / "videos"]
        while pending:
            parent = pending.pop()
            for path in parent.iterdir():
                reject_link(path, path.lstat())
                if path.is_dir():
                    pending.append(path)
                elif path.is_file() and path.suffix.lower() in EXTENSIONS:
                    found.append(path)
        return sorted(found, key=lambda p: p.relative_to(self.root).as_posix().encode("utf-8"))

    def accept(self, video_id, raw):
        number, payload, meta = parse(raw)
        if meta is not None:
            self.db.execute(
                "INSERT OR IGNORE INTO task VALUES(1,?)", (json.dumps(meta, sort_keys=True),)
            )
        digest = hashlib.sha256(payload).hexdigest()
        self.db.execute(
            "INSERT OR IGNORE INTO packets VALUES(?,?,?,?)",
            (number, digest, hashlib.md5(payload).hexdigest().upper(), payload),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO receipts VALUES(?,?,?,?)", (video_id, number, digest, now())
        )

    def invalidate(self, video_id):
        self.db.execute("DELETE FROM receipts WHERE video_id=?", (video_id,))
        self.db.execute(
            "DELETE FROM packets WHERE NOT EXISTS (SELECT 1 FROM receipts r WHERE r.packet_id=packets.packet_id AND r.digest=packets.digest)"
        )

    def scan(self, path, *, cancelled=None, progress=None, rescan=False):
        name = path.relative_to(self.root).as_posix()
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO videos(path) VALUES(?)", (name,))
        row = self.db.execute("SELECT * FROM videos WHERE path=?", (name,)).fetchone()
        video_id = row["id"]
        try:
            signature = fingerprint(path)
        except OSError as exc:
            with self.db:
                self.invalidate(video_id)
                self.db.execute(
                    "UPDATE videos SET status='failed',error=?,ended=?,active=1 WHERE id=?",
                    (str(exc), now(), video_id),
                )
            return "failed"
        changed = signature != (row["size"], row["mtime_ns"], row["sha256"])
        if row["status"] == "completed" and not changed and row["active"] and not rescan:
            if progress:
                progress("skipped", row["processed_frames"], row["total_frames"])
            return "skipped"
        with self.db:
            if changed:
                self.invalidate(video_id)
            self.db.execute(
                """UPDATE videos SET size=?,mtime_ns=?,sha256=?,active=1,status='processing',
                processed_frames=0,total_frames=NULL,valid_frames=0,invalid_frames=0,
                started=?,ended=NULL,error=NULL,attempts=attempts+1 WHERE id=?""",
                (*signature, now(), video_id),
            )
        valid = invalid = 0
        try:
            for index, total, codes, recognition_error in frames(path):
                if cancelled and cancelled():
                    raise InterruptedError("Decode interrupted")
                if recognition_error:
                    invalid += 1
                    self.logger.warning("%s frame %s: %s", name, index, recognition_error)
                for raw in codes:
                    try:
                        self.accept(video_id, raw)
                        valid += 1
                    except (ValueError, UnicodeError) as exc:
                        invalid += 1
                        self.logger.warning("%s frame %s: %s", name, index, exc)
                self.db.execute(
                    "UPDATE videos SET processed_frames=?,total_frames=?,valid_frames=?,invalid_frames=? WHERE id=?",
                    (index, total, valid, invalid, video_id),
                )
                if index % 25 == 0:
                    self.db.commit()  # Packet observations and checkpoint commit together.
                if progress:
                    progress("processing", index, total)
            if fingerprint(path) != signature:
                self.db.rollback()
                with self.db:
                    self.invalidate(video_id)
                raise OSError("Video changed during scan; its packet observations were invalidated")
            self.db.execute(
                "UPDATE videos SET status='completed',ended=? WHERE id=?", (now(), video_id)
            )
            self.db.commit()
            if progress:
                progress("completed", index, total)
            return "completed"
        except BaseException as exc:
            self.db.rollback()
            if not isinstance(exc, (KeyboardInterrupt, InterruptedError)):
                try:
                    changed_during_failure = fingerprint(path) != signature
                except OSError:
                    changed_during_failure = True
                if changed_during_failure:
                    with self.db:
                        self.invalidate(video_id)
            with self.db:
                self.db.execute(
                    "UPDATE videos SET status='failed',ended=?,error=? WHERE id=?",
                    (now(), f"{type(exc).__name__}: {exc}", video_id),
                )
            self.logger.error("%s: %s", name, exc)
            if isinstance(exc, (KeyboardInterrupt, InterruptedError)):
                raise InterruptedError("Decode interrupted") from None
            if not isinstance(exc, (OSError, ValueError, RuntimeError)):
                raise
            return "failed"

    def run(self, *, cancelled=None, progress=None, max_folder_bytes=8 * 1024**3, rescan=False):
        if max_folder_bytes <= 0:
            raise ValueError("Folder verification budget must be positive")
        counts = {"completed": 0, "skipped": 0, "failed": 0}
        interrupted = False
        paths = self.discover()
        present = {path.relative_to(self.root).as_posix() for path in paths}
        with self.db:
            for row in self.db.execute("SELECT id,path FROM videos WHERE active=1"):
                if row["path"] not in present:
                    self.invalidate(row["id"])
                    self.db.execute(
                        "UPDATE videos SET active=0,status='failed',error='Source removed' WHERE id=?",
                        (row["id"],),
                    )
        for number, path in enumerate(paths, 1):

            def on_progress(status, index, total, number=number):
                if progress:
                    progress(number, len(paths), status, index, total)

            try:
                counts[
                    self.scan(path, cancelled=cancelled, progress=on_progress, rescan=rescan)
                ] += 1
            except InterruptedError:
                interrupted = True
                break
        return self.report(counts, len(paths), interrupted, max_folder_bytes)

    def atomic_report(self, name, writer):
        safe_directory(self.root / "reports")
        destination = self.root / "reports" / name
        if destination.exists() or destination.is_symlink():
            reject_link(destination, destination.lstat())
        temporary = destination.with_name(f".{uuid.uuid4().hex}.part")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                writer(stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def report(self, counts, total_videos, interrupted, max_folder_bytes):
        row = self.db.execute("SELECT metadata FROM task WHERE id=1").fetchone()
        meta = json.loads(row[0]) if row else None
        total = meta["total_packets"] if meta else None
        packet_conflicts = self.db.execute(
            "SELECT COUNT(*) FROM (SELECT packet_id FROM packets WHERE packet_id<? GROUP BY packet_id HAVING COUNT(DISTINCT digest)>1)",
            (START_ID,),
        ).fetchone()[0]
        starts, meta_conflicts = 0, 0
        for start in self.db.execute(
            "SELECT payload,digest,content_md5 FROM packets WHERE packet_id=?",
            (START_ID,),
        ):
            from qrft.encoder2100.protocol import frame

            try:
                payload = bytes(start[0])
                if (
                    hashlib.sha256(payload).hexdigest() != start[1]
                    or hashlib.md5(payload).hexdigest().upper() != start[2]
                ):
                    raise ValueError("Persisted START checksum invalid")
                _, _, actual = parse(frame(payload, START_ID))
                if actual == meta:
                    starts += 1
                else:
                    meta_conflicts += 1
            except (ValueError, UnicodeError) as exc:
                meta_conflicts += 1
                self.logger.error("Persisted START: %s", exc)
        predicate, arguments = "packet_id>=0 AND packet_id<?", (START_ID,)
        invalid_packets = 0
        if meta:
            predicate = "packet_id>=0 AND packet_id<? AND ((packet_id<? AND LENGTH(payload)=?) OR (packet_id=? AND LENGTH(payload) BETWEEN 1 AND ?))"
            arguments = (total, total - 1, meta["chunk_size"], total - 1, meta["chunk_size"])
            invalid_packets = self.db.execute(
                "SELECT COUNT(*) FROM packets WHERE packet_id<? AND NOT (" + predicate + ")",
                (START_ID, *arguments),
            ).fetchone()[0]
        valid_ids = (
            "SELECT DISTINCT packet_id FROM packets WHERE " + predicate + " ORDER BY packet_id"
        )
        received = self.db.execute(
            "SELECT COUNT(*) FROM (" + valid_ids + ")", arguments
        ).fetchone()[0]
        missing = None if total is None else total - received
        result = {
            "status": "INCOMPLETE",
            "protocol": meta["protocol"] if meta else None,
            "task_id": identity(meta) if meta else None,
            "source": meta,
            "wire_file_size": None,
            "videos_total": total_videos,
            "videos_completed": counts["completed"],
            "videos_failed": counts["failed"],
            "videos_skipped": counts["skipped"],
            "total_packets": total,
            "received_packets": received,
            "missing_packets": missing,
            "packet_conflicts": packet_conflicts,
            "invalid_packets": invalid_packets,
            "metadata_conflicts": meta_conflicts,
            "trusted_start": bool(starts),
            "finish_seen": bool(
                self.db.execute(
                    "SELECT 1 FROM packets WHERE packet_id=? LIMIT 1", (FINISH_ID,)
                ).fetchone()
            ),
            "interrupted": interrupted,
            "expected_md5": meta["expected_md5"] if meta else None,
            "actual_md5": None,
            "actual_size": None,
            "md5_verified": False,
            "output_path": None,
            "completed_at": now(),
            "error": None,
            "video_errors": [
                dict(r)
                for r in self.db.execute(
                    "SELECT path,status,error FROM videos WHERE error IS NOT NULL ORDER BY path LIMIT 100"
                )
            ],
        }

        def write_missing(stream):
            stream.write(
                f"# Protocol: {result['protocol'] or 'UNKNOWN'}\n# Total packets: {total}\n# Received packets: {received}\n# Missing packets: {missing if missing is not None else 'UNKNOWN (START unavailable)'}\n"
            )
            if total is not None:
                cursor = 0
                for packet in self.db.execute(valid_ids, arguments):
                    for number in range(cursor, packet[0]):
                        stream.write(f"{number:08d}\n")
                    cursor = packet[0] + 1
                for number in range(cursor, total):
                    stream.write(f"{number:08d}\n")

        self.atomic_report("missing_packets.txt", write_missing)
        if packet_conflicts or meta_conflicts:
            result.update(
                status="FAILED",
                error="Conflicting packets or multiple transfer metadata; isolate source videos",
            )
        elif invalid_packets:
            result.update(status="FAILED", error="DATA ID/length inconsistent with locked metadata")
        elif interrupted:
            result["error"] = "Interrupted; committed observations retained"
        elif meta and starts and missing == 0:
            try:
                result.update(self.restore(meta, max_folder_bytes))
            except (ValueError, OSError, BadZipFile, zlib.error, RuntimeError) as exc:
                result.update(status="FAILED", error=str(exc))
        else:
            result["error"] = "Metadata/START unavailable" if not starts else "Missing DATA packets"
        self.atomic_report(
            "decode_result.json",
            lambda stream: json.dump(result, stream, ensure_ascii=False, indent=2),
        )
        return result

    def restore(self, meta, max_folder_bytes):
        safe_directory(self.root / "output")
        temporary = self.root / "output" / f".qrft-{uuid.uuid4().hex}.part"
        destination = self.root / "output" / meta["filename"]
        md5, sha, size, expected_id = hashlib.md5(), hashlib.sha256(), 0, 0
        try:
            with temporary.open("xb") as stream:
                for row in self.db.execute(
                    "SELECT packet_id,digest,content_md5,payload FROM packets WHERE packet_id<? ORDER BY packet_id",
                    (START_ID,),
                ):
                    packet_id, digest, content_md5, payload = row
                    payload = bytes(payload)
                    if (
                        packet_id != expected_id
                        or not valid_data(meta, packet_id, payload)
                        or hashlib.sha256(payload).hexdigest() != digest
                        or hashlib.md5(payload).hexdigest().upper() != content_md5
                    ):
                        raise ValueError("Persisted DATA checksum/order/length invalid")
                    stream.write(payload)
                    md5.update(payload)
                    sha.update(payload)
                    size += len(payload)
                    expected_id += 1
                stream.flush()
                os.fsync(stream.fileno())
            if expected_id != meta["total_packets"]:
                raise ValueError("Packet count mismatch")
            actual_md5, actual_sha = md5.hexdigest().upper(), sha.hexdigest().upper()
            checked = {"actual_md5": actual_md5, "actual_sha256": actual_sha, "actual_size": size}
            if actual_md5 != meta["expected_md5"]:
                return {
                    **checked,
                    "status": "FAILED",
                    "md5_verified": False,
                    "error": "File MD5 mismatch",
                }
            try:
                folder = verify_folder(temporary, max_folder_bytes)
            except (ValueError, OSError, BadZipFile, zlib.error, RuntimeError) as exc:
                return {
                    **checked,
                    "status": "FAILED",
                    "md5_verified": True,
                    "folder": {"status": "FAILED", "auto_extracted": False},
                    "error": str(exc),
                }
            if destination.exists() or destination.is_symlink():
                reject_link(destination, destination.lstat())
                owned = self.db.execute(
                    "SELECT * FROM outputs WHERE name=?", (meta["filename"],)
                ).fetchone()
                if owned is None or owned["md5"] != actual_md5 or owned["size"] != size:
                    raise FileExistsError("Output exists and is not this project's verified output")
                with destination.open("rb") as old:
                    if hashlib.file_digest(old, "sha256").hexdigest().upper() != actual_sha:
                        raise FileExistsError(
                            "Existing verified output was modified; refusing overwrite"
                        )
            else:
                # Record the verified candidate before publication: a crash immediately
                # after the atomic link must not strand a valid but unowned final file.
                with self.db:
                    self.db.execute(
                        "INSERT OR REPLACE INTO outputs VALUES(?,?,?,?)",
                        (meta["filename"], size, actual_md5, actual_sha),
                    )
                os.link(temporary, destination)  # Atomic publication, fails if destination exists.
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO outputs VALUES(?,?,?,?)",
                    (meta["filename"], size, actual_md5, actual_sha),
                )
            return {
                "status": "SUCCESS",
                "actual_md5": actual_md5,
                "actual_sha256": actual_sha,
                "actual_size": size,
                "md5_verified": True,
                "output_path": destination.relative_to(self.root).as_posix(),
                "folder": folder,
            }
        finally:
            temporary.unlink(missing_ok=True)


def decode_project(root, **kwargs):
    with Project(root) as project:
        return project.run(**kwargs)

"""Real v2 SQLite packet stress and bounded recovery; explicitly no QR video."""

from __future__ import annotations

import sqlite3
import statistics
import time

from qrft.acceptance.benchmark import byte_equal, hashes
from qrft.acceptance.resources import BackgroundMonitor, ProcessSampler, environment, save_json
from qrft.control.packets import ingest, init_schema
from qrft.control.recovery import recover
from qrft.control.session import bind_start, init_session
from qrft.core.missing import stream_missing
from qrft.core.protocol import ProtocolError
from qrft.core.protocol_v2 import encode_data_v2, encode_start_v2


def query_benchmark(db, total):
    result = {}
    for label, sql, args in (
        ("count", "SELECT COUNT(*) FROM packets WHERE task_id=?", (1,)),
        (
            "page",
            "SELECT packet_id FROM packets WHERE task_id=? AND packet_id>=? ORDER BY packet_id LIMIT 1000",
            (1, total // 2),
        ),
        ("lookup", "SELECT digest FROM packets WHERE task_id=? AND packet_id=?", (1, total // 2)),
    ):
        measurements = []
        for _ in range(20):
            then = time.perf_counter()
            db.execute(sql, args).fetchall()
            measurements.append(time.perf_counter() - then)
        result[label] = {
            "median_seconds": statistics.median(measurements),
            "max_seconds": max(measurements),
            "query_plan": [list(row) for row in db.execute("EXPLAIN QUERY PLAN " + sql, args)],
            "timer": time.get_clock_info("perf_counter").implementation,
            "timer_api": "perf_counter",
        }
    return result


def remeasure_queries(root, file_mib):
    directory = root / f"storage-{file_mib}mib"
    path = directory / "packets.sqlite3"
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        total = db.execute("SELECT COUNT(*) FROM packets WHERE task_id=1").fetchone()[0]
        report = {
            "scope": "read-only query retest of completed packet store",
            "stored_packets": total,
            "queries": query_benchmark(db, total),
            "clock_resolution_seconds": time.get_clock_info("perf_counter").resolution,
        }
    save_json(directory / "query-perf.json", report)
    return report


def run(root, budget, file_mib=100):
    directory = root / f"storage-{file_mib}mib"
    directory.mkdir(exist_ok=False)
    started = time.monotonic()
    size = file_mib * 1024**2
    budget.check(reserve_bytes=size * 5, force=True)
    source = directory / f"storage-{file_mib}mib.bin"
    sampler = ProcessSampler(directory / "resources.jsonl")
    db = None
    report = {
        "environment": environment(),
        "scope": "SQLite v2 packet store / stream recovery, NO QR video",
    }
    try:
        with BackgroundMonitor(sampler, budget, started) as monitor:
            block = bytes(range(256)) * 4096
            with source.open("xb") as stream:
                for _ in range(file_mib):
                    monitor.check()
                    stream.write(block)
            expected = hashes(source)
            total = (size + 1399) // 1400
            meta = {"filename": source.name, "md5": expected["md5"], "total_packets": total}
            db = sqlite3.connect(directory / "packets.sqlite3")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA cache_size=-2048")
            init_schema(db)
            init_session(db)
            bind_start(db, 1, encode_start_v2(meta))
            db.commit()
            ingest_started = time.monotonic()
            with source.open("rb") as stream:
                for parity in (1, 0):
                    for offset, packet in enumerate(range(parity, total, 2), 1):
                        stream.seek(packet * 1400)
                        assert (
                            ingest(db, 1, encode_data_v2(packet, stream.read(1400))) == "inserted"
                        )
                        if offset % 1000 == 0:
                            monitor.check()
                            db.commit()
                    db.commit()
            report["ingest_seconds"] = time.monotonic() - ingest_started
            report["ingest_packets_per_second"] = total / report["ingest_seconds"]
            report["queries"] = query_benchmark(db, total)
            # Thousands of holes, followed by real selective reinsertion.
            gaps = range(0, total, 100)
            with db:
                db.executemany(
                    "DELETE FROM packets WHERE task_id=1 AND packet_id=?", ((i,) for i in gaps)
                )
            export_started = time.monotonic()
            count = stream_missing(
                directory / "large-missing",
                total,
                (
                    r[0]
                    for r in db.execute(
                        "SELECT packet_id FROM packets WHERE task_id=1 ORDER BY packet_id"
                    )
                ),
            )
            assert count == len(gaps)
            report["missing_export"] = {
                "count": count,
                "seconds": time.monotonic() - export_started,
                "formats": ["txt", "csv", "json"],
            }
            incomplete = recover(db, 1, directory / "incomplete")
            assert incomplete["status"] == "incomplete"
            assert not (directory / "incomplete" / "files").exists()
            with source.open("rb") as stream, db:
                for packet in gaps:
                    stream.seek(packet * 1400)
                    assert ingest(db, 1, encode_data_v2(packet, stream.read(1400))) == "inserted"
            with source.open("rb") as stream:
                raw = encode_data_v2(0, stream.read(1400))
            with db:
                for _ in range(20):
                    assert ingest(db, 1, raw) == "duplicate"
                bind_start(db, 2, encode_start_v2(meta))
                assert ingest(db, 2, raw) == "inserted"
                assert ingest(db, 2, encode_data_v2(0, b"x" * 1400)) == "conflict"
            try:
                recover(db, 2, directory / "conflict")
            except ProtocolError as exc:
                assert "conflict" in str(exc)
            else:
                raise AssertionError("conflicting content was published")
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            db.close()
            db = sqlite3.connect(directory / "packets.sqlite3")
            db.row_factory = sqlite3.Row
            then = time.monotonic()
            result = recover(db, 1, directory / "recovered")
            report["recovery_seconds"] = time.monotonic() - then
            assert result["status"] == "verified" and result["md5"] == expected["md5"]
            assert result["sha256"] == expected["sha256"]
            assert byte_equal(source, directory / "recovered" / "files" / source.name)
            blocked = directory / "unwritable-output"
            blocked.write_bytes(b"owned regular file occupying directory path")
            try:
                recover(db, 1, blocked)
            except OSError:
                pass
            else:
                raise AssertionError("unwritable output path accepted")
            try:
                recover(db, 1, directory / "recovered")
            except FileExistsError:
                pass
            else:
                raise AssertionError("existing user-style file overwritten")
            assert hashes(directory / "recovered" / "files" / source.name) == expected
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            report.update(
                status="PASS",
                source_bytes=size,
                stored_packets=total,
                hashes=expected,
                bytes_equal=True,
                recovered_after_database_reopen=True,
                sqlite_integrity_check="ok",
                duplicate_checks=20,
                quarantined_conflict_count=1,
                no_finish_v2_recovery="complete packets and valid final MD5 accepted as specified",
                incomplete_not_published=True,
                unwritable_output_rejected=True,
                existing_file_protected=True,
                database_bytes=(directory / "packets.sqlite3").stat().st_size,
            )
        report["resources"] = sampler.summary()
        report["total_seconds"] = time.monotonic() - started
        report["budget"] = budget.snapshot()
        save_json(directory / "report.json", report)
        return report
    finally:
        if db:
            db.close()
        sampler.close()

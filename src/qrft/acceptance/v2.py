"""Optional actual-EXE v2 acceptance; synthetic video is explicitly identified."""

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path


def png_video(images: Path, output: Path, *, omit=None, check=lambda: None):
    import cv2
    import numpy as np

    paths = [images / "00000000-start.png"] * 20
    paths += [p for p in sorted(images.glob("*-data.png")) if int(p.name[:8]) != omit]
    paths += [images / "99999999-finish.png"] * 20
    if output.exists():
        raise FileExistsError(output)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"MJPG"), 20, (926, 926))
    if not writer.isOpened():
        writer.release()
        raise OSError("cannot create synthetic v2 AVI")
    previous, image = None, None
    try:
        for path in paths:
            check()
            if path != previous:
                image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
                previous = path
            if image is None:
                raise OSError(f"cannot load {path}")
            h, w = image.shape[:2]
            if max(h, w) > 926:
                raise ValueError("QR image exceeds v2 canvas")
            canvas = np.full((926, 926, 3), 255, dtype=np.uint8)
            y, x = (926 - h) // 2, (926 - w) // 2
            canvas[y : y + h, x : x + w] = image
            writer.write(canvas)
    finally:
        writer.release()
    return len(paths) / 20


def run_v2(runner):
    r = runner
    root = r.root / "v2"
    root.mkdir(exist_ok=False)
    source = root / "中文,全部字节.bin"
    payload = bytes(range(256)) * 5 + secrets.token_bytes(1525)
    source.write_bytes(payload)
    md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest().upper()
    sha = hashlib.sha256(payload).hexdigest()
    images = root / "png"
    r.run("QRFT-Encoder-CLI", "export", source, "--protocol", "v2", "--output", images)
    full = root / "full.avi"
    png_video(images, full, check=r.check)
    r.run("QRFT-Decoder", full, "--protocol", "v2", "--output", root / "local")
    verification = json.loads((root / "local/verification.json").read_text(encoding="utf-8"))
    if verification.get("md5") != md5 or r.hash_file(Path(verification["path"])) != sha:
        raise ValueError("v2 local file MD5/SHA256 mismatch")
    r.control()
    task = r.api("/tasks", {"name": "v2独占验收", "protocol_version": 2})["id"]
    video = root / "lost.avi"
    duration = png_video(images, video, omit=1, check=r.check)
    vid = r.api("/videos", {"task_id": task, "path": str(video), "duration_seconds": duration})[
        "id"
    ]
    # Only this runner's own isolated DB; create short real ranges for a small video.
    with sqlite3.connect(r.env["QRFT_DB_PATH"]) as db:
        db.execute("DELETE FROM slices WHERE video_id=?", (vid,))
        db.executemany(
            "INSERT INTO slices(video_id,start_ms,end_ms) VALUES (?,?,?)",
            [(vid, 0, 1050), (vid, 1050, int(duration * 1000))],
        )
    r.workers(2)
    slices = r.api(f"/slices?video_id={vid}")
    if len({s["owner"] for s in slices}) != 2 or any(s["state"] != "done" for s in slices):
        raise ValueError("v2 needs two independent completed Worker ranges")
    missing = r.api(f"/tasks/{task}/missing")
    if missing["missing_ids"] != [1]:
        raise ValueError(f"unexpected v2 missing list: {missing}")
    if r.api(f"/tasks/{task}/recover", {})["status"] != "incomplete":
        raise ValueError("missing v2 data must not publish a file")
    for fmt in ("txt", "csv", "json"):
        (root / f"missing.{fmt}").write_bytes(
            r.api(f"/tasks/{task}/missing/download?format={fmt}", raw=True)
        )
    retransmit = root / "retransmit-png"
    r.run(
        "QRFT-Encoder-CLI",
        "export",
        source,
        "--protocol",
        "v2",
        "--output",
        retransmit,
        "--retransmit",
        root / "missing.txt",
    )
    repair = root / "repair.avi"
    seconds = png_video(retransmit, repair, check=r.check)
    r.api("/videos", {"task_id": task, "path": str(repair), "duration_seconds": seconds})
    r.workers(1)
    result = r.api(f"/tasks/{task}/recover", {})
    if (
        result.get("md5") != md5
        or result.get("status") != "verified"
        or r.hash_file(Path(result["path"])) != sha
    ):
        raise ValueError("v2 retransmission final MD5/SHA256 mismatch")
    r.evidence(
        "v2-evidence.json",
        {
            "task_id": task,
            "slices": slices,
            "missing_before": missing,
            "recovery": result,
            "local": verification,
        },
    )
    return {
        "protocol_version": 2,
        "source_md5": md5,
        "restored_md5": result["md5"],
        "source_sha256": sha,
        "restored_sha256": result["sha256"],
        "file_bytes": len(payload),
        "scope": "实际 EXE + 1400字节/50%二维码 + 20fps合成AVI；不是Windows录屏或双机SMB",
    }

"""无界面分布式解码节点：从 SMB 视频时间片读取并向控制中心提交原始帧。"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from qrft.core.protocol import encode_data, encode_finish, encode_start
from qrft.decoder.video import iter_video_frames

logger = logging.getLogger(__name__)


def request_json(base_url: str, token: str, route: str, payload: dict) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + route,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    # Claim is not retried: a lost response must expire before another allocation.
    attempts = 1 if route == "/slices/claim" else 4
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == attempts - 1:
                raise
        time.sleep(min(2**attempt, 8))
    return None


def process_slice(
    base_url: str,
    token: str,
    node_id: str,
    lease: dict,
    *,
    sample_fps: float = 10.0,
    batch_size: int = 50,
    maintenance_seconds: float = 30.0,
) -> int:
    """直接访问租约提供的视频路径，不复制或上传视频。"""
    if batch_size <= 0 or maintenance_seconds <= 0:
        raise ValueError("batch_size must be positive")
    video = Path(lease["path"])
    task_id = lease["task_id"]
    batch: list[str] = []
    sent = 0
    fenced = {"lease_token": lease["lease_token"]} if "lease_token" in lease else {}

    def flush() -> None:
        nonlocal sent
        if batch:
            request_json(
                base_url,
                token,
                "/packets/batch",
                {
                    "task_id": task_id,
                    "frames_base64": batch,
                    **({"slice_id": lease["id"], **fenced} if fenced else {}),
                },
            )
            sent += len(batch)
            batch.clear()

    stop = threading.Event()
    errors: list[OSError | ValueError] = []

    def maintain() -> None:
        while not stop.wait(maintenance_seconds):
            try:
                request_json(base_url, token, "/nodes/heartbeat", {"node_id": node_id})
                request_json(
                    base_url,
                    token,
                    f"/slices/{lease['id']}/renew",
                    {"node_id": node_id, "lease_seconds": 120, **fenced},
                )
            except (OSError, ValueError) as exc:
                errors.append(exc)
                return

    thread = threading.Thread(target=maintain, name="qrft-lease", daemon=True)
    thread.start()
    last_checkpoint = time.monotonic()

    def sampled(checkpoint_ms):
        nonlocal last_checkpoint
        if errors:
            raise errors[0]
        if time.monotonic() - last_checkpoint >= 5:
            flush()
            request_json(
                base_url,
                token,
                f"/slices/{lease['id']}/checkpoint",
                {"node_id": node_id, **fenced, "checkpoint_ms": checkpoint_ms},
            )
            last_checkpoint = time.monotonic()

    try:
        for frame in iter_video_frames(
            video,
            sample_fps=sample_fps,
            start_seconds=max(lease["start_ms"], lease.get("checkpoint_ms", 0) - 1000) / 1000,
            end_seconds=lease["end_ms"] / 1000,
            **({"on_sample": sampled} if fenced else {}),
        ):
            if errors:
                raise errors[0]
            if frame.kind == "start":
                request_json(
                    base_url,
                    token,
                    "/tasks/manifest",
                    {
                        "task_id": task_id,
                        "start_base64": base64.b64encode(encode_start(frame.metadata or {})).decode(
                            "ascii"
                        ),
                    },
                )
            elif frame.kind == "finish":
                batch.append(base64.b64encode(encode_finish()).decode("ascii"))
            elif frame.kind == "data":
                batch.append(
                    base64.b64encode(encode_data(frame.packet_id, frame.payload)).decode("ascii")
                )
                if len(batch) >= batch_size:
                    flush()
        if errors:
            raise errors[0]
        flush()
        stop.set()
        thread.join()
        if errors:
            raise errors[0]
        request_json(
            base_url, token, f"/slices/{lease['id']}/complete", {"node_id": node_id, **fenced}
        )
    finally:
        stop.set()
        thread.join()
    return sent


def run_worker(
    base_url: str,
    token: str,
    node_id: str,
    *,
    poll_seconds: float = 5.0,
    once: bool = False,
) -> None:
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    while True:
        try:
            request_json(base_url, token, "/nodes/heartbeat", {"node_id": node_id})
            lease = request_json(
                base_url, token, "/slices/claim", {"node_id": node_id, "lease_seconds": 120}
            )
        except OSError:
            logger.exception("Control request failed")
            if once:
                raise
            time.sleep(poll_seconds)
            continue
        if lease is not None:
            try:
                process_slice(base_url, token, node_id, lease)
            except (OSError, ValueError):
                logger.exception("Slice %s failed; lease will expire for reassignment", lease["id"])
                if once:
                    raise
        if once:
            return
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 分布式 SMB 视频解码节点")
    parser.add_argument("--config", type=Path, help="UTF-8 JSON 配置文件")
    parser.add_argument("--server", help="控制中心 HTTP 地址")
    parser.add_argument("--token", help="API Token（推荐 QRFT_API_TOKEN 环境变量）")
    parser.add_argument("--node-id")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    config = {}
    if args.config:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8-sig"))
            if not isinstance(config, dict):
                raise TypeError("configuration must be an object")
        except (OSError, ValueError, TypeError) as exc:
            parser.error(f"Cannot read configuration: {type(exc).__name__}")
    args.server = args.server or config.get("server")
    args.node_id = args.node_id or config.get("node_id")
    args.token = args.token or os.environ.get("QRFT_API_TOKEN") or config.get("token")
    if not all(
        isinstance(value, str) and value for value in (args.server, args.node_id, args.token)
    ):
        parser.error("server, node-id and token must be configured")
    logging.basicConfig(level=logging.INFO)
    try:
        run_worker(
            args.server,
            args.token,
            args.node_id,
            poll_seconds=args.poll_seconds,
            once=args.once,
        )
    except KeyboardInterrupt:
        logger.info("Worker stopped; unfinished lease will expire")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

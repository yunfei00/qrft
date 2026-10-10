"""无界面分布式解码节点：从 SMB 视频时间片读取并向控制中心提交原始帧。"""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

from qrft.core.protocol import encode_data, encode_start
from qrft.decoder.video import iter_video_frames


def request_json(base_url: str, token: str, route: str, payload: dict) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + route,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def process_slice(
    base_url: str,
    token: str,
    node_id: str,
    lease: dict,
    *,
    sample_fps: float = 10.0,
    batch_size: int = 50,
) -> int:
    """直接访问租约提供的视频路径，不复制或上传视频。"""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    video = Path(lease["path"])
    task_id = lease["task_id"]
    batch: list[str] = []
    sent = 0

    def flush() -> None:
        nonlocal sent
        if batch:
            request_json(
                base_url,
                token,
                "/packets/batch",
                {"task_id": task_id, "frames_base64": batch},
            )
            sent += len(batch)
            batch.clear()

    for frame in iter_video_frames(
        video,
        sample_fps=sample_fps,
        start_seconds=lease["start_ms"] / 1000,
        end_seconds=lease["end_ms"] / 1000,
    ):
        if frame.kind == "start":
            request_json(
                base_url, token, "/tasks/manifest",
                {
                    "task_id": task_id,
                    "start_base64": base64.b64encode(encode_start(frame.metadata or {})).decode(
                        "ascii"
                    ),
                },
            )
        elif frame.kind == "data":
            batch.append(
                base64.b64encode(encode_data(frame.packet_id, frame.payload)).decode("ascii")
            )
            if len(batch) >= batch_size:
                flush()
    flush()
    request_json(base_url, token, f"/slices/{lease['id']}/complete", {"node_id": node_id})
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
        request_json(base_url, token, "/nodes/heartbeat", {"node_id": node_id})
        lease = request_json(
            base_url, token, "/slices/claim", {"node_id": node_id, "lease_seconds": 3600}
        )
        if lease is not None:
            process_slice(base_url, token, node_id, lease)
        if once:
            return
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 分布式 SMB 视频解码节点")
    parser.add_argument("--server", required=True, help="控制中心 HTTP 地址")
    parser.add_argument("--token", required=True, help="API Token")
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    run_worker(
        args.server,
        args.token,
        args.node_id,
        poll_seconds=args.poll_seconds,
        once=args.once,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

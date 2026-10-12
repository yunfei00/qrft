"""Managed source processes and authenticated desktop API client; no Qt dependency."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class ControlClient:
    def __init__(self, server: str, token: str):
        url = urllib.parse.urlsplit(server)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.query:
            raise ValueError("服务器地址须为 HTTP(S) 地址，不能包含口令或查询参数")
        self.server = server.rstrip("/")
        self.token = token

    def request(self, route: str, payload=None, *, download: Path | None = None):
        request = urllib.request.Request(
            self.server + route,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if download is not None:
                    with download.open("xb") as stream:
                        while block := response.read(65536):
                            stream.write(block)
                    return str(download)
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read(16384).decode("utf-8", errors="replace")
            raise RuntimeError(f"控制中心请求失败 ({exc.code}): {detail}") from None
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"网络或文件操作失败：{type(exc).__name__}：{exc}") from None


def inspect_video(path: Path) -> dict:
    import cv2

    video = cv2.VideoCapture(str(path))
    try:
        if not video.isOpened():
            raise OSError(f"无法读取视频，请检查路径、格式或 SMB 只读权限：{path}")
        fps = video.get(cv2.CAP_PROP_FPS)
        frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frames <= 0:
            raise ValueError(f"视频时长/FPS 无效：{path}")
        return {
            "path": str(path.resolve()),
            "duration_seconds": frames / fps,
            "fps": fps,
            "frames": int(frames),
            "width": int(video.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
    finally:
        video.release()


class ManagedSession:
    """Only owns processes started here; persistent task data is never removed."""

    def __init__(self, workspace: Path, *, server: str | None = None, token: str = ""):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.state = self.workspace / ".qrft-decoder"
        owner = "QRFT managed decoder workspace v1\n"
        if self.state.exists():
            if self.state.is_symlink() or not (self.state / "OWNER.txt").is_file():
                raise ValueError("任务目录没有 QRFT 所有权标记，请选择新的工作目录")
            if (self.state / "OWNER.txt").read_text() != owner:
                raise ValueError("任务目录所有权标记不匹配")
        else:
            self.state.mkdir()
            (self.state / "OWNER.txt").write_text(owner)
        self.logs = self.state / "logs"
        for child in (self.logs, self.state / "control.sqlite3", self.state / "outputs"):
            if child.is_symlink():
                raise ValueError("任务日志、数据库或结果路径不能是符号链接")
        self.logs.mkdir(exist_ok=True)
        self.control: subprocess.Popen | None = None
        self.workers: list[subprocess.Popen] = []
        self.active_task = None
        self.handles = []
        self.token = token if server else secrets.token_urlsafe(32)
        self.env = {
            **os.environ,
            "QRFT_API_TOKEN": self.token,
            "QRFT_DB_PATH": str(self.state / "control.sqlite3"),
            "QRFT_OUTPUT_DIR": str(self.state / "outputs"),
            "PYTHONUNBUFFERED": "1",
        }
        self.env.pop("QRFT_ACCEPTANCE_ID", None)
        if server:
            self.client = ControlClient(server, token)
            self.client.request("/tasks")
        else:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            self.client = ControlClient(f"http://127.0.0.1:{port}", self.token)
            self.control = self.spawn("control", "qrft.control.app", "--port", str(port))
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if self.control.poll() is not None:
                        raise RuntimeError("本地控制中心退出；请查看 control 日志")
                    try:
                        self.client.request("/tasks")
                        break
                    except RuntimeError:
                        time.sleep(0.1)
                else:
                    raise TimeoutError("本地控制中心启动超时")
            except BaseException:
                self.close()
                raise

    def spawn(self, label, module, *args):
        log = (self.logs / f"{label}-{uuid.uuid4().hex[:8]}.log").open("xb")
        self.handles.append(log)
        return subprocess.Popen(
            [sys.executable, "-m", module, *args],
            env=self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def start(self, task_id: int, count: int = 1, sample_fps: float = 60):
        if not 1 <= count <= 16 or sample_fps <= 0:
            raise ValueError("Worker 数量或采样参数无效")
        self.stop_workers()
        if self.active_task and self.active_task != task_id:
            self.client.request(f"/tasks/{self.active_task}/pause", {})
        self.client.request(f"/tasks/{task_id}/pause", {})
        self.active_task = task_id
        nodes = set()
        try:
            for _ in range(count):
                node = f"desktop-{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
                nodes.add(node)
                self.workers.append(
                    self.spawn(
                        node,
                        "qrft.decoder.worker",
                        "--server",
                        self.client.server,
                        "--node-id",
                        node,
                        "--task-id",
                        str(task_id),
                        "--poll-seconds",
                        "0.2",
                        "--lease-seconds",
                        "15",
                        "--maintenance-seconds",
                        "3",
                        "--sample-fps",
                        str(sample_fps),
                    )
                )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                registered = {node["node_id"] for node in self.client.request("/nodes")}
                if nodes <= registered:
                    break
                if any(process.poll() is not None for process in self.workers):
                    raise RuntimeError("Worker 启动失败；请查看节点日志")
                time.sleep(0.1)
            else:
                raise TimeoutError("等待本机 Worker 心跳超时")
            self.client.request(f"/tasks/{task_id}/resume", {})
        except BaseException:
            self.stop_workers()
            raise

    def stop_workers(self):
        for process in self.workers:
            if process.poll() is None:
                process.terminate()
        for process in self.workers:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.workers.clear()

    def pause(self, task_id: int):
        self.stop_workers()
        return self.client.request(f"/tasks/{task_id}/pause", {})

    def close(self):
        self.stop_workers()
        if self.control is not None and self.control.poll() is None:
            self.control.terminate()
            self.control.wait(timeout=5)
        for handle in self.handles:
            handle.close()
        self.handles.clear()

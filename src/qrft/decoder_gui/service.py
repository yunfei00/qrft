"""Managed decoder processes and authenticated desktop API client; no Qt dependency."""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
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
        path = urllib.parse.urlsplit(route).path
        method = "GET" if payload is None else "POST"
        retryable = method == "GET" or (
            path == "/nodes/heartbeat"
            or path in {"/tasks/manifest", "/packets/batch"}
            or re.fullmatch(r"/tasks/\d+/(pause|resume|cancel)", path) is not None
            or re.fullmatch(r"/slices/\d+/(renew|checkpoint|error)", path) is not None
            or re.fullmatch(r"/videos/\d+/rescan", path) is not None
        )
        attempts = 3 if retryable else 1
        for attempt in range(attempts):
            request = urllib.request.Request(
                self.server + route,
                data=None if payload is None else json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    if download is not None:
                        if download.exists():
                            raise FileExistsError(download)
                        staging = None
                        try:
                            with tempfile.NamedTemporaryFile(
                                dir=download.parent, delete=False
                            ) as stream:
                                staging = Path(stream.name)
                                received = 0
                                while block := response.read(65536):
                                    stream.write(block)
                                    received += len(block)
                                expected = response.headers.get("Content-Length")
                                if expected is not None and received != int(expected):
                                    raise OSError("缺包报告下载不完整")
                                stream.flush()
                                os.fsync(stream.fileno())
                            os.link(staging, download)
                        finally:
                            if staging is not None:
                                staging.unlink(missing_ok=True)
                        return str(download)
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if retryable and exc.code in {500, 502, 503, 504} and attempt + 1 < attempts:
                    time.sleep(0.1 * (2**attempt))
                    continue
                detail = exc.read(16384).decode("utf-8", errors="replace")
                raise RuntimeError(f"控制中心请求失败 ({exc.code}): {detail}") from None
            except (ConnectionError, TimeoutError, urllib.error.URLError) as exc:
                if retryable and attempt + 1 < attempts:
                    time.sleep(0.1 * (2**attempt))
                    continue
                raise RuntimeError(
                    f"网络或文件操作失败 [{route}]：{type(exc).__name__}：{exc}"
                ) from None
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"网络或文件操作失败 [{route}]：{type(exc).__name__}：{exc}"
                ) from None


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
        if getattr(sys, "frozen", False):
            command = [
                sys.executable,
                {"qrft.control.app": "control", "qrft.decoder.worker": "worker"}[module],
                *args,
            ]
        else:
            command = [sys.executable, "-m", module, *args]
        return subprocess.Popen(
            command,
            env=self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    def set_task_flag(self, task_id: int, action: str, field: str, expected: bool):
        try:
            return self.client.request(f"/tasks/{task_id}/{action}", {})
        except RuntimeError:
            # The server may commit an idempotent state change before a local
            # socket aborts its response. Reconcile through the durable state API
            # before reporting failure or starting/stopping more processes.
            try:
                state = self.client.request(f"/tasks/{task_id}/progress")
            except RuntimeError:
                pass
            else:
                if bool(state.get(field)) == expected:
                    return state
            raise

    def set_task_paused(self, task_id: int, paused: bool):
        return self.set_task_flag(task_id, "pause" if paused else "resume", "paused", paused)

    def cancel(self, task_id: int):
        self.stop_workers()
        return self.set_task_flag(task_id, "cancel", "cancelled", True)

    def start(self, task_id: int, count: int = 1, sample_fps: float = 60):
        if not 1 <= count <= 16 or sample_fps <= 0:
            raise ValueError("Worker 数量或采样参数无效")
        self.stop_workers()
        if self.active_task and self.active_task != task_id:
            self.set_task_paused(self.active_task, True)
        self.set_task_paused(task_id, True)
        self.active_task = task_id
        nodes = set()
        try:
            for _ in range(count):
                node = f"desktop-{uuid.uuid4().hex[:16]}"
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
            self.set_task_paused(task_id, False)
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
        return self.set_task_paused(task_id, True)

    def close(self):
        self.stop_workers()
        if self.control is not None and self.control.poll() is None:
            self.control.terminate()
            self.control.wait(timeout=5)
        for handle in self.handles:
            handle.close()
        self.handles.clear()

"""在独占目录中操作真实 EXE，保留视频、API 快照和进程日志。"""

from __future__ import annotations

import hashlib
import json
import locale
import os
import platform
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil

from qrft import __version__
from qrft.acceptance.metrics import Monitor
from qrft.acceptance.report import ITEMS, write_reports
from qrft.acceptance.smb import Blocked, controller_role, worker_role
from qrft.acceptance.v2 import run_v2

PROGRAMS = ("QRFT-Encoder-CLI", "QRFT-Encoder-GUI", "QRFT-Decoder", "QRFT-Control")


def decode_console(content, encoding=None):
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode(encoding or locale.getencoding(), errors="replace")


class Cancelled(Exception):
    pass


class Runner:
    def __init__(
        self,
        programs: Path,
        output: Path,
        *,
        selected=None,
        cancel=None,
        notify=None,
        size_bytes=10 * 1024**2,
        stability_seconds=600,
        role="local",
        smb_server="",
        smb_share="",
        smb_video="",
        smb_token="",
        smb_port=8788,
    ):
        self.programs = programs.resolve()
        self.root = output.resolve() / ("qrft-acceptance-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True, exist_ok=False)
        (self.root / "OWNER.txt").write_text("QRFT acceptance owned resources", encoding="utf-8")
        self.cancel = cancel or threading.Event()
        self.notify = notify or (lambda *args: None)
        self.selected = set(selected if selected is not None else ITEMS)
        self.size_bytes = size_bytes
        self.stability_seconds = stability_seconds
        self.role, self.smb_server, self.smb_share, self.smb_video, self.smb_port = (
            role,
            smb_server,
            smb_share,
            smb_video,
            smb_port,
        )
        self.token = smb_token or secrets.token_urlsafe(32)
        self.expected_instance = self.root.name
        self.env = {
            **os.environ,
            "QRFT_API_TOKEN": self.token,
            "QRFT_DB_PATH": str(self.root / "control.db"),
            "QRFT_OUTPUT_DIR": str(self.root / "recovered"),
            "QRFT_ACCEPTANCE_ID": self.root.name,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
        self.processes = []
        self.process_logs = {}
        self.lock = threading.Lock()
        self.base = ""
        self.server = None
        self.source = self.root / "中文随机二进制.exe"
        self.payload = bytes(range(256)) + secrets.token_bytes(64)
        self.source.write_bytes(self.payload)
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.images = self.root / "png"
        self.video = self.root / "完整视频.avi"
        self.counter = 0
        self.results = []

    def log(self, message):
        message = str(message).replace(self.token, "[已隐藏]")
        with self.lock, (self.root / "acceptance.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now(UTC).isoformat()} {message}\n")
        self.notify("log", message)

    def check(self):
        if self.cancel.is_set():
            raise Cancelled("用户取消，已结束自有测试进程")

    def pause(self, seconds):
        if self.cancel.wait(seconds):
            self.check()

    def binary(self, name):
        path = self.programs / name / f"{name}.exe"
        if not path.is_file():
            raise FileNotFoundError(f"缺少完整程序目录：{path}")
        return path

    def spawn(self, name, *args, extra_env=None):
        self.check()
        with self.lock:
            self.counter += 1
            log = self.root / f"process-{self.counter}-{name}.log"
        self.log(f"启动 {name}，日志 {log.name}")
        with log.open("xb") as stream:
            process = subprocess.Popen(
                [str(self.binary(name)), *map(str, args)],
                cwd=self.root,
                env={**self.env, **(extra_env or {})},
                stdout=stream,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        with self.lock:
            self.processes.append(process)
            self.process_logs[process.pid] = log
        return process

    def wait(self, process, timeout=120):
        deadline = time.monotonic() + timeout
        offset = 0

        def tail():
            nonlocal offset
            with self.process_logs[process.pid].open("rb") as stream:
                stream.seek(offset)
                content = stream.read(65536)
                offset = stream.tell()
            if content:
                self.log(decode_console(content).rstrip())

        while process.poll() is None:
            self.check()
            tail()
            if time.monotonic() >= deadline:
                self.stop(process)
                raise TimeoutError("测试进程超时；请查看进程日志")
            self.pause(0.1)
        tail()
        if process.returncode:
            raise RuntimeError(f"EXE 返回错误码 {process.returncode}；请查看进程日志")

    def run(self, name, *args, timeout=120, extra_env=None):
        self.wait(self.spawn(name, *args, extra_env=extra_env), timeout)

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def api(self, route, body=None, *, raw=False):
        self.check()
        if self.server is not None and self.server.poll() is not None:
            raise RuntimeError("自有控制中心已退出；停止发送请求")
        request = urllib.request.Request(
            self.base + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-QRFT-Acceptance-ID": self.expected_instance,
            },
        )
        # 本地验收不经系统代理；Token 只进入请求头和子进程环境。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=10) as response:
                content = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(8192).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {route}：{detail}") from None
        return content if raw else json.loads(content)

    def environment(self):
        if platform.system() != "Windows":
            raise OSError("实际 EXE 验收要求 Windows")
        free = shutil.disk_usage(self.root).free
        if free < 200 * 1024**2:
            raise OSError("可用磁盘空间不足 200 MB")
        for name in PROGRAMS:
            self.binary(name)
        checksum = self.programs / "SHA256SUMS.txt"
        if not checksum.is_file():
            raise OSError("缺少 SHA256SUMS.txt，无法确认构建完整性")
        verified = 0
        listed = set()
        for line in checksum.read_text(encoding="utf-8-sig").splitlines():
            self.check()
            digest, relative = line.split("  ", 1)
            path = (self.programs / relative).resolve()
            if not path.is_relative_to(self.programs):
                raise ValueError("校验清单包含越界路径")
            if self.hash_file(path) != digest.lower():
                raise ValueError(f"构建文件校验失败：{relative}")
            listed.add(path)
            verified += 1
        for name in (*PROGRAMS, "QRFT-Acceptance"):
            for path in (self.programs / name).rglob("*"):
                if path.is_file() and path.resolve() not in listed:
                    raise ValueError(f"程序文件未列入校验清单：{path.name}")
        if not verified:
            raise ValueError("校验清单为空")
        version = (self.programs / "VERSION.txt").read_text(encoding="utf-8-sig").strip()
        if version != __version__:
            raise ValueError(f"验收器与套件版本不一致：{version} / {__version__}")
        (self.root / "BUILD-SHA256SUMS.txt").write_bytes(checksum.read_bytes())
        return {
            "disk_free_bytes": free,
            "verified_build_files": verified,
            "build_manifest_sha256": self.hash_file(checksum),
            "bundle_version": version,
        }

    def hash_file(self, path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024**2):
                self.check()
                digest.update(chunk)
        return digest.hexdigest()

    def encoder(self):
        if not self.images.exists():
            self.run(
                "QRFT-Encoder-CLI",
                "export",
                self.source,
                "--output",
                self.images,
                "--chunk-size",
                64,
            )
        self.run("QRFT-Encoder-GUI", "--smoke-test", extra_env={"QT_QPA_PLATFORM": "offscreen"})
        self.run(
            "QRFT-Encoder-CLI",
            "play",
            self.source,
            "--interval-ms",
            10,
            "--initial-delay-ms",
            0,
            "--windowed",
            "--exit-when-finished",
            extra_env={"QT_QPA_PLATFORM": "offscreen"},
        )
        return {"png_count": len(list(self.images.glob("*.png"))), "source_sha256": self.sha}

    def make_video(self, images, output, *, omit=None):
        import cv2
        import numpy as np

        paths = [
            images / "00000000-start.png",
            *sorted(images.glob("*-data.png")),
            images / "99999999-finish.png",
        ]
        paths = [p for p in paths if p.name != omit]

        def load(path):
            image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise OSError(f"PNG 无法读取：{path.name}")
            return image

        height, width = load(paths[0]).shape[:2]
        writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"MJPG"), 5, (width, height))
        if not writer.isOpened():
            raise OSError("无法创建 AVI")
        try:
            for path in paths:
                image = cv2.resize(load(path), (width, height), interpolation=cv2.INTER_NEAREST)
                for _ in range(30):
                    self.check()
                    writer.write(image)
        finally:
            writer.release()
        return len(paths) * 6

    def ensure_video(self):
        if not self.images.exists():
            self.encoder()
        if not self.video.exists():
            self.make_video(self.images, self.video)

    def decoder(self):
        self.ensure_video()
        self.run("QRFT-Decoder", self.video, "--output", self.root / "local", "--sample-fps", 5)
        digest = self.hash_file(self.root / "local" / self.source.name)
        if digest != self.sha:
            raise ValueError("本地解码 SHA256 不一致")
        return {"source_sha256": self.sha, "restored_sha256": digest, "video": str(self.video)}

    def control(self):
        if self.server is not None:
            return {"health": self.api("/health")}
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        if self.role == "controller":
            port = self.smb_port
            self.base = f"http://127.0.0.1:{port}"
        self.server = self.spawn(
            "QRFT-Control",
            "--port",
            port,
            "--host",
            "0.0.0.0" if self.role == "controller" else "127.0.0.1",
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                health = self.api("/health")
                if health.get("acceptance_instance") != self.root.name:
                    raise RuntimeError(
                        "控制中心实例不匹配；端口可能被其他服务占用，未操作该服务的任务"
                    )
                return {"health": health}
            except (OSError, urllib.error.URLError):
                if self.server.poll() is not None:
                    raise RuntimeError("控制中心启动失败") from None
                self.pause(0.1)
        raise TimeoutError("控制中心启动超时")

    def workers(self, count):
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [
                pool.submit(
                    self.run,
                    "QRFT-Decoder",
                    "worker",
                    "--server",
                    self.base,
                    "--node-id",
                    f"acceptance-{self.counter}-{i}",
                    "--once",
                )
                for i in range(count)
            ]
            for future in futures:
                future.result()

    def task(self, video, duration):
        self.control()
        task = self.api("/tasks", {"name": "验收独占任务"})["id"]
        vid = self.api(
            "/videos", {"task_id": task, "path": str(video), "duration_seconds": duration}
        )["id"]
        return task, vid

    def recover(self, task):
        started = time.monotonic()
        result = self.api(f"/tasks/{task}/recover", {})
        if result["status"] != "verified" or result["sha256"] != self.sha:
            raise ValueError(f"恢复未完成或 SHA256 错误：{result}")
        if self.hash_file(Path(result["path"])) != self.sha:
            raise ValueError("磁盘恢复文件 SHA256 错误")
        result["recovery_seconds"] = time.monotonic() - started
        return result

    def chain(self, count):
        self.ensure_video()
        task, vid = self.task(self.video, 42)
        started = time.monotonic()
        if count == 1:
            process = self.spawn(
                "QRFT-Decoder",
                "worker",
                "--server",
                self.base,
                "--node-id",
                "acceptance-single",
                "--poll-seconds",
                0.1,
            )
            try:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    slices = self.api(f"/slices?video_id={vid}")
                    if all(s["state"] == "done" for s in slices):
                        break
                    if process.poll() is not None:
                        raise RuntimeError("单 Worker 提前退出")
                    self.pause(0.1)
                else:
                    raise TimeoutError("单 Worker 扫描超时")
            finally:
                self.stop(process)
        else:
            self.workers(count)
        slices = self.api(f"/slices?video_id={vid}")
        if not all(s["state"] == "done" for s in slices):
            raise ValueError("时间片未全部完成")
        if count == 2 and len({s["owner"] for s in slices}) != 2:
            raise ValueError("没有两个独立 Worker 完成不同时间片")
        result = self.recover(task)
        duration = time.monotonic() - started
        snapshot = {
            "slices": slices,
            "progress": self.api(f"/tasks/{task}/progress"),
            "recovery": result,
            "worker_metrics": self.api(f"/acceptance/slices?video_id={vid}"),
        }
        self.evidence(f"task-{task}.json", snapshot)
        return {
            "task_id": task,
            "source_sha256": self.sha,
            "restored_sha256": result["sha256"],
            "effective_packets_per_second": 5 / duration,
            "effective_bytes_per_second": len(self.payload) / duration,
            "chain_seconds": duration,
            "recovery_seconds": result["recovery_seconds"],
            "scope": "真实 EXE + 合成 AVI；不是屏幕录制传输",
        }

    def missing(self):
        self.ensure_video()
        lost = self.root / "丢包视频.avi"
        duration = self.make_video(self.images, lost, omit="00000002-data.png")
        task, _ = self.task(lost, duration)
        self.workers(2)
        missing = self.api(f"/tasks/{task}/missing")
        if missing["missing_ids"] != [2]:
            raise ValueError(f"缺包列表错误：{missing}")
        incomplete = self.api(f"/tasks/{task}/recover", {})
        if incomplete["status"] != "incomplete":
            raise ValueError("缺包时不应输出最终文件")
        for fmt in ("txt", "csv", "json"):
            (self.root / f"missing.{fmt}").write_bytes(
                self.api(f"/tasks/{task}/missing/download?format={fmt}", raw=True)
            )
        started = time.monotonic()
        images = self.root / "补传png"
        self.run(
            "QRFT-Encoder-CLI",
            "export",
            self.source,
            "--output",
            images,
            "--chunk-size",
            64,
            "--retransmit",
            self.root / "missing.txt",
        )
        video = self.root / "补传视频.avi"
        duration = self.make_video(images, video)
        self.api("/videos", {"task_id": task, "path": str(video), "duration_seconds": duration})
        self.workers(1)
        result = self.recover(task)
        self.evidence(f"retransmit-{task}.json", {"missing": missing, "recovery": result})
        return {
            "loss_rate": 1 / 5,
            "retransmit_seconds": time.monotonic() - started,
            "source_sha256": self.sha,
            "restored_sha256": result["sha256"],
        }

    def fault(self):
        """实际 Worker 被终止；真实 HTTP 代理注入两次 503，租约过期后重新处理。"""
        self.ensure_video()
        task, vid = self.task(self.video, 42)
        target = self.base
        lock = threading.Lock()
        failures = [0]
        victim_token = [None]
        release_response = threading.Event()
        runner = self

        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # 禁止把请求头/Token 写入日志。

            def do_POST(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with lock:
                    fail = self.path == "/packets/batch" and failures[0] < 2
                    if fail:
                        failures[0] += 1
                if fail:
                    self.send_response(503)
                    self.end_headers()
                    return
                request = urllib.request.Request(
                    target + self.path,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {runner.token}",
                        "X-QRFT-Acceptance-ID": runner.expected_instance,
                        "Content-Type": "application/json",
                    },
                )
                try:
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                        request, timeout=10
                    ) as response:
                        content = response.read()
                        code = response.status
                except urllib.error.HTTPError as exc:
                    content, code = exc.read(), exc.code
                except OSError:
                    content, code = b"upstream unavailable", 503
                if (
                    self.path == "/packets/batch"
                    and code == 200
                    and json.loads(data).get("lease_token") == victim_token[0]
                ):
                    # 保留已入库 DATA，同时让故障节点停留在真实 HTTP 请求中，避免快速扫描抢先完成。
                    release_response.wait(10)
                self.send_response(code)
                self.end_headers()
                try:
                    self.wfile.write(content)
                except OSError:
                    pass

        proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        proxy.daemon_threads = True
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{proxy.server_port}"
        try:
            victim = self.spawn(
                "QRFT-Decoder",
                "worker",
                "--server",
                address,
                "--node-id",
                "fault-victim",
                "--once",
                "--lease-seconds",
                3,
                "--maintenance-seconds",
                0.5,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                slices = self.api(f"/slices?video_id={vid}")
                if any(s["owner"] == "fault-victim" and s["state"] == "leased" for s in slices):
                    initial_lease = next(s for s in slices if s["owner"] == "fault-victim")
                    victim_token[0] = initial_lease["lease_token"]
                    break
                self.pause(0.05)
            else:
                raise TimeoutError("未观察到 Worker 领取租约")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                before_exit = self.api(f"/packets/{task}/stats")
                if before_exit["stored"] > 0:
                    break
                self.pause(0.05)
            else:
                raise TimeoutError("故障节点未提交可持久化数据包")
            active = next(
                s for s in self.api(f"/slices?video_id={vid}") if s["owner"] == "fault-victim"
            )
            if active["lease_until"] <= initial_lease["lease_until"]:
                raise ValueError("没有观察到扫描和重试期间的续租")
            self.stop(victim)
            release_response.set()
            self.pause(3.5)
            for index in range(2):
                self.run(
                    "QRFT-Decoder",
                    "worker",
                    "--server",
                    address,
                    "--node-id",
                    f"fault-replacement-{index}",
                    "--once",
                    "--lease-seconds",
                    15,
                    "--maintenance-seconds",
                    1,
                )
            result = self.recover(task)
            slices = self.api(f"/slices?video_id={vid}")
            if not any(s["attempts"] >= 2 for s in slices) or failures[0] != 2:
                raise ValueError("故障或重新分配证据不足")
            self.evidence(
                f"fault-{task}.json",
                {
                    "slices": slices,
                    "injected_http_503": failures[0],
                    "killed_worker_returncode": victim.returncode,
                    "recovery": result,
                    "packets_before_exit": before_exit,
                    "initial_lease": initial_lease,
                    "renewed_lease": active,
                },
            )
            return {
                "injected_http_503": failures[0],
                "lease_reallocated": True,
                "packets_persisted_before_exit": before_exit["stored"],
                "renewal_observed": True,
                "restored_sha256": result["sha256"],
                "scope": "本地 HTTP 503 模拟短暂网络故障；真实子进程异常退出",
            }
        finally:
            release_response.set()
            proxy.shutdown()
            proxy.server_close()
            thread.join(timeout=5)

    def stability(self):
        if not 1 <= self.stability_seconds <= 3600:
            raise ValueError("稳定性测试时长必须为 1 至 3600 秒")
        evidence = self.root / "gui-stability.json"
        self.run(
            "QRFT-Encoder-GUI",
            "--stability-file",
            self.source,
            "--stability-seconds",
            self.stability_seconds,
            "--stability-evidence",
            evidence,
            timeout=self.stability_seconds + 30,
        )
        result = json.loads(evidence.read_text(encoding="utf-8"))
        if (
            result["error"]
            or result["displayed_frames"] < 1
            or result["elapsed_seconds"] < self.stability_seconds
        ):
            raise ValueError("GUI 播放失败、没有帧或提前退出")
        return {
            **result,
            "duration_seconds": self.stability_seconds,
            "scope": "实际 Qt 窗口连续播放；未进行屏幕录制或传输质量验收",
        }

    def performance(self):
        if not 1 <= self.size_bytes <= 10 * 1024**3:
            raise ValueError("自定义大小应在 1 字节至 10 GB 之间")
        if shutil.disk_usage(self.root).free < self.size_bytes + 200 * 1024**2:
            raise OSError("空间不足，未创建大文件")
        source = self.root / "性能独占随机文件.bin"
        block = secrets.token_bytes(min(self.size_bytes, 1024**2))
        remaining = self.size_bytes
        with source.open("xb") as stream:
            while remaining:
                self.check()
                chunk = block[: min(len(block), remaining)]
                stream.write(chunk)
                remaining -= len(chunk)
        started = time.perf_counter()
        digest = self.hash_file(source)
        seconds = max(time.perf_counter() - started, 1e-9)
        return {
            "scope": "仅文件 SHA256 哈希性能；未测二维码传输",
            "file_bytes": self.size_bytes,
            "hash_seconds": seconds,
            "hash_bytes_per_second": self.size_bytes / seconds,
            "sha256": digest,
        }

    def evidence(self, name, value):
        with (self.root / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)

    def qr_performance(self):
        from qrft.decoder.video import iter_video_frames

        self.ensure_video()
        samples = 0

        def sampled(_):
            nonlocal samples
            self.check()
            samples += 1

        started = time.perf_counter()
        frames = sum(1 for _ in iter_video_frames(self.video, sample_fps=5, on_sample=sampled))
        seconds = max(time.perf_counter() - started, 1e-9)
        if not frames:
            raise ValueError("合成 AVI 没有识别出合法二维码")
        return {
            "scope": "真实 CLI PNG + 小规模合成 AVI + ZXing 核心；不是录屏或大文件传输",
            "decoded_qr_frames": frames,
            "sampled_video_frames": samples,
            "unrecognized_sample_fraction": max(0, samples - frames) / max(samples, 1),
            "zxing_seconds": seconds,
            "decoded_qr_frames_per_second": frames / seconds,
        }

    def execute(self):
        started = datetime.now(UTC).isoformat()
        environment_failed = False
        handlers = {
            "environment": self.environment,
            "encoder": self.encoder,
            "decoder": self.decoder,
            "control": self.control,
            "single": lambda: self.chain(1),
            "dual": lambda: self.chain(2),
            "missing": self.missing,
            "performance": self.performance,
            "qr_performance": self.qr_performance,
            "v2": lambda: run_v2(self),
            "fault": self.fault,
            "stability": self.stability,
            "smb": lambda: worker_role(self) if self.role == "worker" else controller_role(self),
        }
        try:
            for item in ITEMS:
                result = {
                    "id": item,
                    "status": "pending",
                    "metrics": {},
                    "evidence": str(self.root),
                }
                self.results.append(result)
                if item not in self.selected:
                    result.update(status="skipped", reason="未选择")
                elif self.cancel.is_set():
                    result.update(status="skipped", reason="用户取消")
                elif environment_failed:
                    result.update(status="blocked", reason="环境检查失败，无法启动后续验收")
                elif item not in handlers:
                    result.update(
                        status="blocked",
                        reason={
                            "smb": "真实双机 SMB：未验收；需要第二台 Windows 与共享访问证据",
                            "fault": "故障注入尚未执行",
                            "stability": "长时间 GUI 实测尚未执行",
                        }[item],
                    )
                else:
                    result["status"] = "running"
                    result["started_at"] = datetime.now(UTC).isoformat()
                    self.notify("result", dict(result))
                    self.log(f"开始：{ITEMS[item]}")
                    timer = time.monotonic()
                    try:
                        with Monitor(self.processes) as monitor:
                            result["metrics"] = handlers[item]()
                        result["metrics"].update(monitor.result())
                        result["status"] = "passed"
                    except Blocked as exc:
                        result.update(status="blocked", reason=str(exc))
                    except Cancelled as exc:
                        result.update(status="skipped", reason=str(exc))
                    except Exception as exc:  # noqa: BLE001 - boundary preserves failure evidence
                        result.update(
                            status="failed",
                            reason=f"{type(exc).__name__}: {exc}".replace(self.token, "[已隐藏]"),
                        )
                    result["duration_seconds"] = time.monotonic() - timer
                    result["ended_at"] = datetime.now(UTC).isoformat()
                self.notify("result", dict(result))
                if item == "environment" and result["status"] == "failed":
                    environment_failed = True
                self.log(f"{ITEMS[item]}：{result['status']} {result.get('reason', '')}")
        finally:
            for process in reversed(self.processes):
                self.stop(process)
        report = {
            "schema_version": 1,
            "version": __version__,
            "started_at": started,
            "ended_at": datetime.now(UTC).isoformat(),
            "machine": {
                "os": platform.platform(),
                "hostname": platform.node(),
                "processor": platform.processor(),
                "cpu_count": os.cpu_count(),
                "memory_total_bytes": psutil.virtual_memory().total,
            },
            "build_commit": (self.programs / "COMMIT.txt").read_text(encoding="utf-8-sig").strip()
            if (self.programs / "COMMIT.txt").is_file()
            else "unknown",
            "environment": {
                "programs_directory": str(self.programs),
                "data_directory": str(self.root),
                "video_kind": "synthetic AVI",
            },
            "log": str(self.root / "acceptance.log"),
            "results": self.results,
        }
        write_reports(self.root, report)
        self.notify("finished", str(self.root / "report.html"))
        return report

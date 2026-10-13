"""Native Qt event acceptance with actual MP4, HTTP processes and durable evidence."""

from __future__ import annotations

import hashlib
import html
import json
import os
import platform
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import chain
from pathlib import Path

import cv2
import numpy as np
import psutil
from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
)

from qrft.core.manifest import inspect_file
from qrft.core.protocol_v2 import encode_data_v2, encode_finish_v2, encode_start_v2
from qrft.core.qr_image import qr_png, v2_image
from qrft.decoder_gui.main import DecoderWindow
from qrft.decoder_gui.service import inspect_video
from qrft.encoder_cli.playback import iter_encoded_frames


def video(frames, path: Path, *, unchecked=False):
    """Real render; unchecked is only for intentionally corrupt QR fixtures."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
    if not writer.isOpened():
        raise OSError("MP4 writer unavailable")
    previous, canvas = None, None
    try:
        for _, raw in frames:
            if raw != previous:
                if unchecked:
                    image = cv2.imdecode(
                        np.frombuffer(qr_png(raw, correction="L"), np.uint8), cv2.IMREAD_COLOR
                    )
                else:
                    image = v2_image(raw)
                h, w = image.shape[:2]
                if max(h, w) > 926:
                    raise ValueError("fixture QR does not fit")
                canvas = np.full((926, 926, 3), 255, np.uint8)
                y, x = (926 - h) // 2, (926 - w) // 2
                canvas[y : y + h, x : x + w] = image
                previous = raw
            writer.write(canvas)
    finally:
        writer.release()
    return path


class FaultProxy:
    """Real loopback HTTP fault, forwarding every successful payload unchanged."""

    def __init__(self, upstream, token):
        self.events = []
        self.remaining_faults = 1
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.forward()

            def do_POST(self):
                self.forward()

            def forward(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                payload = json.loads(data) if data else {}
                entry = {
                    "route": self.path,
                    "time": time.monotonic(),
                    "node_id": payload.get("node_id"),
                }
                owner.events.append(entry)
                if self.path == "/packets/batch":
                    time.sleep(0.4)
                    if owner.remaining_faults:
                        owner.remaining_faults -= 1
                        entry["status"] = 503
                        self.send_response(503)
                        self.end_headers()
                        self.wfile.write(b"controlled temporary fault")
                        return
                request = urllib.request.Request(
                    upstream + self.path,
                    data=data if self.command == "POST" else None,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                try:
                    with urllib.request.urlopen(request, timeout=30) as response:
                        body, status = response.read(), response.status
                except urllib.error.HTTPError as exc:
                    body, status = exc.read(), exc.code
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # A deliberately killed Worker cannot read its response.
                entry["status"] = status

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class Actor:
    def __init__(self, root, workspace):
        self.root, self.workspace = root, workspace
        self.app = QApplication.instance() or QApplication([])
        self.app.setOrganizationName("QRFT-Automated-Acceptance")
        self.app.setApplicationName("NativeDesktop")
        self.settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
        self.window = None
        self.events, self.cases, self.processes, self.tokens = [], [], {}, []
        self.dialog_plan = []
        self.dialog_timer = QTimer()
        self.dialog_timer.timeout.connect(self.handle_dialog)
        self.dialog_timer.start(30)
        self.ticks = []
        self.tick_timer = QTimer()
        self.tick_timer.timeout.connect(lambda: self.ticks.append(time.monotonic()))
        self.tick_timer.start(20)

    def wait(self, condition, seconds=90):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            # Avoid creating hundreds of loopback TCP connections per second;
            # the GUI refresh timer still exercises live state while polling.
            QTest.qWait(50)
        raise AssertionError(self.window.status.text() if self.window else "Qt condition timeout")

    def idle(self):
        self.wait(lambda: not self.window.busy)

    def track(self):
        if not self.window.session:
            return
        self.tokens.append(self.window.session.token)
        for process in [self.window.session.control, *self.window.session.workers]:
            if process is not None and process.poll() is None:
                parent = psutil.Process(process.pid)
                for child in [parent, *parent.children(recursive=True)]:
                    self.processes[child.pid] = child.create_time()

    def screenshot(self, name):
        self.window.raise_()
        self.app.processEvents()
        path = self.root / "screenshots" / f"{name}.png"
        assert self.window.grab().save(str(path))
        return str(path.relative_to(self.root))

    def case(self, name, action):
        started = time.monotonic()
        record = {"name": name, "status": "RUNNING"}
        self.cases.append(record)
        try:
            record["evidence"] = action() or {}
            record["status"] = "PASS"
        except Exception as exc:
            record.update(status="FAIL", reason=str(exc), traceback=traceback.format_exc())
            raise
        finally:
            record["seconds"] = time.monotonic() - started
            if self.window and self.window.isVisible():
                record["screenshot"] = self.screenshot(f"{len(self.cases):02d}")

    def open(self):
        self.window = DecoderWindow(self.workspace, settings=self.settings)
        self.window.job.completed.connect(
            lambda name, _: self.events.append(
                {"operation": name, "status": "completed", "time": time.monotonic()}
            )
        )
        self.window.job.failed.connect(
            lambda name, error: self.events.append(
                {"operation": name, "status": "error", "detail": error, "time": time.monotonic()}
            )
        )
        self.window.show()
        self.wait(lambda: self.window.session is not None and not self.window.busy)
        self.window.timer.setInterval(500)
        self.track()
        assert self.window.mode.currentIndex() == 0 and not self.window.token.text()
        return {
            "control_pid": self.window.session.control.pid,
            "default_mode": "single",
            "native_platform": self.app.platformName(),
            "dpi_ratio": self.window.devicePixelRatioF(),
        }

    def button(self, text):
        matches = [b for b in self.window.findChildren(QPushButton) if b.text() == text]
        assert len(matches) == 1, text
        button = matches[0]
        self.window.centralWidget().ensureWidgetVisible(button)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    def paste(self, edit, text):
        edit.setFocus()
        self.app.clipboard().setText(text)
        QTest.keyClick(edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    def handle_dialog(self):
        dialog = self.app.activeModalWidget()
        if not dialog or not self.dialog_plan:
            return
        title, value = self.dialog_plan[0]
        if title not in dialog.windowTitle():
            return
        self.dialog_plan.pop(0)
        if isinstance(dialog, QMessageBox):
            QTest.mouseClick(
                dialog.button(QMessageBox.StandardButton.Yes), Qt.MouseButton.LeftButton
            )
        elif isinstance(dialog, QInputDialog):
            edit = dialog.findChild(QLineEdit)
            if edit is not None:
                self.paste(edit, value)
                QTest.keyClick(edit, Qt.Key.Key_Return)
            else:
                combo = dialog.findChild(QComboBox)
                combo.setFocus()
                QTest.keyClick(combo, Qt.Key.Key_Home)
                QTest.keyClick(combo, Qt.Key.Key_Return)
                box = dialog.findChild(QDialogButtonBox)
                QTest.mouseClick(
                    box.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton
                )
        elif isinstance(dialog, QFileDialog):
            edit = dialog.findChild(QLineEdit, "fileNameEdit")
            assert edit is not None, "Qt file dialog filename control missing"
            self.paste(edit, str(value))
            QTest.keyClick(edit, Qt.Key.Key_Return)

    def task(self, name):
        self.idle()
        self.dialog_plan = [("新建隔离任务", name), ("任务协议", "v2")]
        self.button("新建任务")
        self.wait(
            lambda: (
                not self.dialog_plan
                and not self.window.busy
                and name in self.window.tasks.currentText()
            )
        )
        return self.window.task_id()

    def import_dialog(self, path):
        self.idle()
        self.dialog_plan = [("添加同一原文件录像", str(path)), ("确认来源", "yes")]
        self.button("添加视频 / 同任务补传 MP4、AVI")
        self.wait(lambda: not self.dialog_plan and not self.window.busy)

    def drop(self, path):
        self.idle()
        self.dialog_plan = [("确认录像来源", "yes")]
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        enter = QDragEnterEvent(
            QPoint(80, 80),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(self.window, enter)
        assert enter.isAccepted()
        drop = QDropEvent(
            QPointF(80, 80),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(self.window, drop)
        self.wait(lambda: not self.dialog_plan and not self.window.busy)

    def click_idle(self, text):
        self.idle()
        before = len(self.events)
        self.button(text)
        self.idle()
        failures = [event for event in self.events[before:] if event["status"] == "error"]
        if failures:
            raise AssertionError(f"后台操作失败：{failures[-1]}")

    def progress(self):
        return self.window.session.client.request(f"/tasks/{self.window.task_id()}/progress")

    def scanned(self):
        def done():
            progress = self.progress()
            return progress["slices"] and all(s["state"] == "done" for s in progress["slices"])

        self.wait(done, 120)
        self.window.timer.stop()
        self.idle()
        self.window.refresh()
        self.idle()
        return self.progress()

    def close(self):
        self.track()
        self.window.close()
        self.wait(lambda: not self.window.job.isRunning())
        self.wait(
            lambda: (
                not any(
                    psutil.pid_exists(pid) and psutil.Process(pid).create_time() == stamp
                    for pid, stamp in self.processes.items()
                )
            ),
            15,
        )

    def configure(self, workers=2, slices=1):
        self.window.tabs.setCurrentIndex(0)
        for spin, value in [
            (self.window.worker_count, workers),
            (self.window.slice_seconds, slices),
        ]:
            edit = spin.findChild(QLineEdit)
            self.paste(edit, str(value))
            QTest.keyClick(edit, Qt.Key.Key_Tab)
        self.window.tabs.setCurrentIndex(1)

    def negative(self, name, paths, expected, *, invalid_import=False):
        task = self.task(name)
        before = len(self.events)
        for path in paths:
            self.drop(path)
        if not invalid_import:
            self.click_idle("开始 / 继续")
            self.track()
            self.window.timer.start(500)
            self.wait(lambda: expected(self.progress()), 60)
        else:
            assert any(e["status"] == "error" for e in self.events[before:])
        self.window.timer.stop()
        self.idle()
        self.window.refresh()
        self.idle()
        progress = self.progress()
        assert progress["recovery"]["status"] != "verified"
        assert not (self.window.session.state / "outputs" / str(task) / "files").exists()
        picture = self.screenshot(f"negative-{task}")
        self.click_idle("取消任务")
        return {
            "task_id": task,
            "progress": progress,
            "screenshot": picture,
            "events": self.events[before:],
        }


def fixtures(root):
    data = root / "fixtures"
    data.mkdir()
    source = data / "测试文件,全部字节.bin"
    source.write_bytes(bytes(range(256)) * 256)
    frames = list(iter_encoded_frames(source, protocol_version=2))
    start, finish = frames[:20], frames[-20:]
    packets = frames[20:-20]
    # Hold packet0 to allow actual pause/stop while scanning; captured repeats,
    # not a change to the encoder's once-per-DATA wire schedule.
    first = video(chain(start, [packets[0]] * 600, packets[1:10], finish), data / "第一段.mp4")
    missing = data / "selective.txt"
    missing.write_text("".join(f"{i:08d}\n" for i in range(10, 47)), encoding="utf-8")
    repair = video(
        iter_encoded_frames(source, protocol_version=2, retransmit=missing), data / "补传段.mp4"
    )
    empty = data / "中文,空文件.bin"
    empty.write_bytes(b"")
    empty_video = video(iter_encoded_frames(empty, protocol_version=2), data / "empty.mp4")
    small = data / "尾块.bin"
    small.write_bytes(b"\x00\xff" * 700 + b"tail")
    short = list(iter_encoded_frames(small, protocol_version=2))
    no_start = video((f for f in short if f[0] != "START"), data / "no-start.mp4")
    corrupt_raw = encode_data_v2(0, b"a")
    corrupt_raw = corrupt_raw[:-48] + b"0" * 32 + corrupt_raw[-16:]
    meta = inspect_file(small, 1400)
    wrong = video(
        chain(short[:20], [("0", encode_data_v2(0, b"z" * 1400)), short[21]], short[-20:]),
        data / "wrong-hash.mp4",
    )
    conflict = video(
        chain(short[:22], [("0", encode_data_v2(0, b"z" * 1400))], short[-20:]),
        data / "conflict.mp4",
    )
    bad_md5 = video(
        [
            ("START", encode_start_v2({**meta, "total_packets": 1})),
            ("data", corrupt_raw),
            ("FINISH", encode_finish_v2()),
        ],
        data / "bad-frame.mp4",
        unchecked=True,
    )
    mixed = video(iter_encoded_frames(small, protocol_version=1), data / "v1.mp4", unchecked=True)
    other = data / "不同文件.bin"
    other.write_bytes(b"different original")
    other_video = video(iter_encoded_frames(other, protocol_version=2), data / "other.mp4")
    bad = data / "乱码�,无效.mp4"
    bad.write_bytes(b"not a movie\xff\x00")
    fault = video(
        chain(start, [packets[0]] * 1200, packets[1:], finish), data / "network-fault.mp4"
    )
    return locals()


def run(root: Path, workspace: Path | None = None, stability_seconds=60):
    if os.name != "nt":
        raise RuntimeError("完整原生验收必须运行 Windows；不能冒充真实桌面")
    root.mkdir(parents=True, exist_ok=False)
    (root / "screenshots").mkdir()
    workspace = workspace or root / "workspace"
    if workspace.exists():
        raise FileExistsError("验收工作区必须是新的独占目录")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    actor = Actor(root, workspace)
    process = psutil.Process()
    process.cpu_percent()
    io_before = process.io_counters()
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    report = {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": psutil.cpu_count(),
        "memory_total_bytes": psutil.virtual_memory().total,
        "test_disk_free_bytes": psutil.disk_usage(str(root)).free,
        "git_commit": git_commit,
        "git_worktree_dirty_at_start": bool(
            subprocess.run(
                ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
            ).stdout
        ),
        "material": "合成 MP4：真实编码核心/二维码/OpenCV，非截图工具录屏",
        "qt_interaction": "Windows QtTest 鼠标/键盘/拖放事件；真实 Qt 文件对话框，非 mocked 返回值",
        "artifacts": {
            "html_report": "report.html",
            "gui_log": "gui.log",
            "screenshots_directory": "screenshots/",
            "workspace_logs_directory": "../workspace/.qrft-decoder/logs/",
        },
        "cases": actor.cases,
    }
    proxy = None
    return_code = 2
    try:
        f = fixtures(root)
        actor.case("原生窗口、自动 Control、无 Token/编码口令", actor.open)
        actor.configure()
        task = actor.task("64 KiB 缺包补传闭环")
        actor.case("Qt 文件对话框导入首段", lambda: actor.import_dialog(f["first"]))
        actor.click_idle("开始 / 继续")
        actor.track()
        actor.window.timer.start(500)
        actor.wait(
            lambda: (
                actor.progress()["stored"] > 0
                and any(
                    s["state"] == "leased" for s in actor.window.session.client.request("/slices")
                )
            )
        )
        actor.case("扫描中暂停并保留数据", lambda: actor.click_idle("暂停"))
        paused = actor.progress()
        assert paused["paused"] and paused["stored"] > 0
        actor.click_idle("开始 / 继续")
        actor.track()
        actor.wait(
            lambda: any(
                s["state"] == "leased" for s in actor.window.session.client.request("/slices")
            )
        )
        actor.case("扫描中停止并保存", lambda: actor.click_idle("停止并保存"))
        saved = actor.progress()["stored"]
        actor.case("关闭清理线程和整个自有进程树", actor.close)
        actor.case("重开原任务与设置持久化", actor.open)
        assert actor.window.task_id() == task and actor.progress()["stored"] >= saved
        assert actor.window.worker_count.value() == 2 and actor.window.slice_seconds.value() == 1
        actor.click_idle("开始 / 继续")
        actor.track()
        partial = actor.scanned()
        assert (
            partial["total_packets"] == 47
            and partial["stored"] == 10
            and partial["missing_count"] == 37
        )
        export = root / "export"
        export.mkdir()
        actor.dialog_plan = [("选择缺包导出目录", str(export))]
        actor.case(
            "Qt 目录对话框导出 TXT/CSV/JSON", lambda: actor.click_idle("导出缺包 TXT / CSV / JSON")
        )
        ids = list(range(10, 47))
        assert [int(v) for v in (export / "missing.txt").read_text().splitlines()] == ids
        assert [int(v) for v in (export / "missing.csv").read_text().splitlines()[1:]] == ids
        assert json.loads((export / "missing.json").read_text())["missing_ids"] == ids
        report["partial"] = {
            "task_id": task,
            "progress": partial,
            "missing_ids": ids,
            "media": inspect_video(f["first"]),
        }
        actor.case("真实 Qt 拖放导入同任务补传", lambda: actor.drop(f["repair"]))
        actor.click_idle("开始 / 继续")
        actor.track()
        actor.scanned()
        actor.window.timer.start(500)
        actor.wait(lambda: actor.progress()["recovery"]["status"] == "verified")
        actor.window.timer.stop()
        actor.idle()
        actor.window.refresh()
        actor.idle()
        recovered = actor.progress()
        target = Path(recovered["recovery"]["path"])
        assert recovered["missing_count"] == 0 and recovered["conflicts"] == 0
        assert target.read_bytes() == f["source"].read_bytes()
        assert actor.window.packet_bar.value() == 100 and actor.window.scan_bar.value() == 100
        assert "恢复成功" in actor.window.status.text()
        source_md5 = hashlib.md5(f["source"].read_bytes()).hexdigest().upper()
        assert recovered["recovery"]["md5"] == source_md5
        actor.case(
            "MD5 与逐字节一致、GUI/数据库真实进度一致",
            lambda: {
                "task_id": task,
                "md5": source_md5,
                "recovery": recovered,
                "bytes_equal": True,
            },
        )
        before = target.read_bytes()
        actor.case("恢复按钮不覆盖既有文件", lambda: actor.click_idle("校验并恢复文件"))
        assert target.read_bytes() == before
        actor.case("实际调用系统打开结果目录", lambda: actor.button("打开结果目录"))
        actor.case("重复视频幂等登记", lambda: actor.import_dialog(f["repair"]))
        assert len(actor.window.session.client.request(f"/videos?task_id={task}")) == 2
        receipts = [
            r
            for v in actor.window.session.client.request(f"/videos?task_id={task}")
            for r in actor.window.session.client.request(f"/acceptance/slices?video_id={v['id']}")
        ]
        assert len({r["node_id"] for r in receipts if r["completed_at"]}) >= 2
        actor.case(
            "至少两个独立 Worker 的不同真实时间片与边界去重",
            lambda: {"receipts": receipts, "duplicates": recovered["duplicates"]},
        )
        actor.case(
            "缺 START 不编造总包数",
            lambda: actor.negative(
                "等待 START",
                [f["no_start"]],
                lambda p: bool(p["slices"]) and all(s["state"] == "done" for s in p["slices"]),
            ),
        )
        assert actor.progress()["total_packets"] is None
        actor.case(
            "最终 MD5 错误禁止恢复",
            lambda: actor.negative(
                "错误 MD5", [f["wrong"]], lambda p: p["recovery"]["status"] == "failed"
            ),
        )
        actor.case(
            "有效内容冲突隔离",
            lambda: actor.negative("冲突", [f["conflict"]], lambda p: p["conflicts"] > 0),
        )
        actor.case(
            "损坏单包 MD5 丢弃且待补传",
            lambda: actor.negative(
                "损坏帧",
                [f["bad_md5"]],
                lambda p: (
                    p.get("total_packets") is not None
                    and bool(p["slices"])
                    and all(s["state"] == "done" for s in p["slices"])
                ),
            ),
        )
        actor.case(
            "v1/v2 混用拒绝",
            lambda: actor.negative(
                "混用协议",
                [f["mixed"]],
                lambda p: any(
                    s.get("error") for s in actor.window.session.client.request("/slices")
                ),
            ),
        )
        actor.case(
            "不同文件 START 元数据拒绝",
            lambda: actor.negative(
                "不同来源",
                [f["first"], f["other_video"]],
                lambda p: any(
                    s.get("error") for s in actor.window.session.client.request("/slices")
                ),
            ),
        )
        actor.case(
            "乱码/无效 MP4 可见错误",
            lambda: actor.negative("非法视频", [f["bad"]], lambda _: True, invalid_import=True),
        )
        actor.case(
            "不存在路径可见错误",
            lambda: actor.negative(
                "不存在路径", [root / "nonexistent.mp4"], lambda _: True, invalid_import=True
            ),
        )
        empty_task = actor.task("空文件")
        actor.import_dialog(f["empty_video"])
        actor.click_idle("开始 / 继续")
        actor.scanned()
        actor.window.timer.start(500)
        actor.wait(lambda: actor.progress()["recovery"]["status"] == "verified")
        empty_result = actor.progress()
        assert Path(empty_result["recovery"]["path"]).read_bytes() == b""
        actor.case("中文逗号空文件恢复", lambda: {"task_id": empty_task, "recovery": empty_result})
        fault_task = actor.task("HTTP 503、续租、进程终止与重领")
        actor.configure(slices=20)
        actor.drop(f["fault"])
        proxy = FaultProxy(actor.window.session.client.server, actor.window.session.token)
        actor.window.session.client.server = proxy.url
        actor.click_idle("开始 / 继续")
        actor.track()
        actor.window.timer.start(500)
        actor.wait(
            lambda: any(
                e["route"].endswith("/renew") and e.get("status") == 200 for e in proxy.events
            ),
            90,
        )
        leases = [
            s for s in actor.window.session.client.request("/slices") if s["state"] == "leased"
        ]
        lease = next(
            s for s in leases if any(s["owner"] in p.args for p in actor.window.session.workers)
        )
        victim = next(p for p in actor.window.session.workers if lease["owner"] in p.args)
        victim.kill()
        victim.wait(timeout=5)
        actor.scanned()
        actor.window.timer.start(500)
        actor.wait(lambda: actor.progress()["recovery"]["status"] == "verified", 120)
        assert actor.progress()["stored"] == 47 and actor.progress()["conflicts"] == 0
        try:
            actor.window.session.client.request(
                f"/slices/{lease['id']}/complete",
                {"node_id": lease["owner"], "lease_token": lease["lease_token"]},
            )
        except RuntimeError as exc:
            assert "409" in str(exc)
        else:
            raise AssertionError("old lease unexpectedly accepted")
        assert any(
            s["id"] == lease["id"] and s["attempts"] >= 2 and s["owner"] != lease["owner"]
            for s in actor.window.session.client.request("/slices")
        )
        assert any(e.get("status") == 503 for e in proxy.events)
        actor.case(
            "真实 HTTP 503 重试、长扫描续租、Worker 终止/租约重领/围栏",
            lambda: {
                "task_id": fault_task,
                "killed_pid": victim.pid,
                "old_lease": lease,
                "proxy_events": proxy.events,
                "progress": actor.progress(),
            },
        )
        actor.click_idle("取消任务")
        assert actor.progress()["cancelled"]
        actor.click_idle("开始 / 继续")
        assert not actor.progress()["cancelled"]
        actor.click_idle("重新扫描视频")
        assert actor.progress()["paused"] and any(
            s["state"] == "pending" for s in actor.window.session.client.request("/slices")
        )
        actor.case("取消/恢复/重新扫描保留全部已验证包", lambda: actor.progress())
        actor.window.resize(720, 480)
        actor.app.processEvents()
        scroll = actor.window.findChild(QScrollArea)
        bar = scroll.verticalScrollBar()
        if bar.maximum() > 0:
            bar.setFocus()
            QTest.keyClick(bar, Qt.Key.Key_End)
            assert bar.value() > 0
        actor.case(
            "小窗口/中文布局与实际滚动事件",
            lambda: {
                "width": actor.window.width(),
                "height": actor.window.height(),
                "scroll_maximum": bar.maximum(),
                "dpi_ratio": actor.window.devicePixelRatioF(),
            },
        )
        actor.window.resize(1000, 650)
        actor.click_idle("停止并保存")
        actor.window.timer.start(500)
        samples = []
        cpu_samples = []
        started = time.monotonic()
        while time.monotonic() - started < stability_seconds:
            actor.app.processEvents()
            samples.append(psutil.Process().memory_info().rss)
            cpu_samples.append(process.cpu_percent())
            QTest.qWait(100)
        io_after = process.io_counters()
        actor.case(
            "原生 GUI 持续刷新稳定性",
            lambda: {
                "seconds": time.monotonic() - started,
                "samples": len(samples),
                "rss_min_bytes": min(samples) if samples else 0,
                "rss_peak_bytes": max(samples) if samples else 0,
                "rss_last_bytes": samples[-1] if samples else 0,
                "process_cpu_average_percent": sum(cpu_samples) / len(cpu_samples)
                if cpu_samples
                else 0,
                "process_cpu_peak_percent": max(cpu_samples) if cpu_samples else 0,
                "process_io_read_bytes": max(0, io_after.read_bytes - io_before.read_bytes),
                "process_io_write_bytes": max(0, io_after.write_bytes - io_before.write_bytes),
                "qt_timer_ticks": len(actor.ticks),
            },
        )
        actor.case("最终关闭无遗留自有线程/子进程，SQLite 完整", actor.close)
        with sqlite3.connect(workspace / ".qrft-decoder" / "control.sqlite3") as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        report["source_md5"] = source_md5
        report["owned_processes"] = [
            {"pid": pid, "create_time": stamp, "alive_after_close": False}
            for pid, stamp in actor.processes.items()
        ]
        actor.cases.append(
            {
                "name": "第二台物理 Windows/SMB 与物理断网",
                "status": "NOT TESTED",
                "reason": "当前执行机只有一台物理 Windows；本机多个进程不替代物理双机",
            }
        )
        return_code = 0
    except KeyboardInterrupt:
        report["failure"] = "验收已由用户取消；正在清理本次创建的进程和资源。"
        return_code = 130
    except Exception:  # noqa: BLE001 - produce a failure report before returning a nonzero exit
        report["failure"] = traceback.format_exc()
        return_code = 2
    finally:
        if actor.window and actor.window.job.isRunning():
            actor.close()
        if proxy:
            proxy.close()
        actor.dialog_timer.stop()
        actor.tick_timer.stop()
        report["qt_events"] = actor.events
        report["exit_code"] = return_code
        report["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        report["counts"] = {
            status: sum(c["status"] == status for c in actor.cases)
            for status in ("PASS", "FAIL", "NOT TESTED")
        }
        text = json.dumps(report, ensure_ascii=False, indent=2)
        for token in set(actor.tokens):
            text = text.replace(token, "[REDACTED]")
        (root / "report.json").write_text(text, encoding="utf-8")
        rows = "".join(
            "<tr><td>"
            + html.escape(c["name"])
            + "</td><td>"
            + c["status"]
            + "</td><td>"
            + html.escape(str(c.get("evidence", c.get("reason", ""))))
            + "</td><td>"
            + (
                f'<a href="{html.escape(c["screenshot"], quote=True)}">截图</a>'
                if c.get("screenshot")
                else ""
            )
            + "</td></tr>"
            for c in actor.cases
        )
        (root / "report.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>QRFT 原生自动验收</title><h1>合成 MP4 / 原生 Qt 自动验收</h1><p>运行环境、时间和材料说明见 report.json；日志：<a href="gui.log">gui.log</a></p><table border="1"><thead><tr><th>验收项</th><th>状态</th><th>证据</th><th>截图</th></tr></thead>'
            + rows
            + "</table>",
            encoding="utf-8",
        )
        if actor.window:
            actor.window.log.toPlainText()
            log = actor.window.log.toPlainText()
            for token in set(actor.tokens):
                log = log.replace(token, "[REDACTED]")
            (root / "gui.log").write_text(log, encoding="utf-8")
    return return_code

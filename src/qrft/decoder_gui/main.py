"""中文单机/分布式解码桌面入口，全部网络和视频操作在后台执行。"""

from __future__ import annotations

import argparse
import json
import queue
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qrft.decoder_gui.service import ManagedSession, inspect_video


class JobQueue(QThread):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.jobs = queue.Queue()

    def run(self):
        while (item := self.jobs.get()) is not None:
            name, operation = item
            try:
                self.completed.emit(name, operation())
            except Exception as exc:  # noqa: BLE001 - report every background failure to the GUI
                self.failed.emit(name, f"{type(exc).__name__}: {exc}")


class DecoderWindow(QMainWindow):
    def __init__(self, workspace: Path | None = None, *, settings=None):
        super().__init__()
        self.setWindowTitle("QRFT 视频解码与文件恢复")
        self.setAcceptDrops(True)
        self.resize(1000, 780)
        if screen := QApplication.primaryScreen():
            area = screen.availableGeometry()
            self.resize(min(1000, area.width() - 40), min(780, area.height() - 80))
        self.settings = settings or QSettings("QRFT", "SourceDecoder")
        self.session = None
        self.busy = False
        self.pending_jobs = 0
        self.closing = False
        self.last_progress = {}
        self.started_at = None
        self.output_path = None
        self.log_offsets = {}
        self.job = JobQueue()
        self.job.completed.connect(self.done)
        self.job.failed.connect(self.failed)
        self.job.start()
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel("视频解码与文件恢复")
        title.setStyleSheet("font-size:22px;font-weight:600;color:#183652")
        layout.addWidget(title)
        layout.addWidget(QLabel("导入同一原文件的视频和补传录像；扫描完成后仍须验证文件哈希。"))
        self.tabs = QTabWidget()
        setup = QWidget()
        form = QFormLayout(setup)
        self.mode = QComboBox()
        self.mode.addItems(["单机模式（自动启动本地服务）", "分布式模式（连接现有控制中心）"])
        form.addRow("运行方式", self.mode)
        default = Path.home() / "QRFT-Decoder-Tasks"
        self.workspace = QLineEdit(str(workspace or self.settings.value("workspace", str(default))))
        browse = QPushButton("选择工作目录")
        browse.clicked.connect(self.choose_workspace)
        row = QHBoxLayout()
        row.addWidget(self.workspace)
        row.addWidget(browse)
        form.addRow("任务与日志目录", row)
        self.server = QLineEdit(str(self.settings.value("server", "http://127.0.0.1:8787")))
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("分布式服务器", self.server)
        form.addRow("API Token（只存内存）", self.token)
        self.sample = QDoubleSpinBox()
        self.sample.setRange(20, 240)
        self.sample.setValue(float(self.settings.value("sample_fps", 60)))
        form.addRow("采样 FPS（默认 60）", self.sample)
        self.worker_count = QSpinBox()
        self.worker_count.setRange(1, 16)
        self.worker_count.setValue(int(self.settings.value("workers", 1)))
        form.addRow("本机独立 Worker 进程数", self.worker_count)
        self.slice_seconds = QSpinBox()
        self.slice_seconds.setRange(1, 3600)
        self.slice_seconds.setValue(int(self.settings.value("slice_seconds", 30)))
        form.addRow("视频时间片（秒，默认 30）", self.slice_seconds)
        self.connect_button = QPushButton("打开工作区 / 连接服务器")
        self.connect_button.clicked.connect(self.connect_session)
        form.addRow(self.connect_button)
        self.tabs.addTab(setup, "设置")
        main = QWidget()
        panel = QVBoxLayout(main)
        task_row = QHBoxLayout()
        self.tasks = QComboBox()
        self.tasks.currentIndexChanged.connect(self.select_task)
        task_row.addWidget(QLabel("当前任务"))
        task_row.addWidget(self.tasks, 1)
        new = QPushButton("新建任务")
        new.clicked.connect(self.new_task)
        task_row.addWidget(new)
        panel.addLayout(task_row)
        self.videos = QTableWidget(0, 3)
        self.videos.setHorizontalHeaderLabels(["视频路径", "时长（秒）", "扫描状态"])
        self.videos.horizontalHeader().setStretchLastSection(True)
        self.videos.setColumnWidth(0, 520)
        panel.addWidget(self.videos)
        import_button = QPushButton("添加视频 / 同任务补传 MP4、AVI")
        import_button.clicked.connect(self.choose_videos)
        panel.addWidget(import_button)
        controls = QHBoxLayout()
        for text, callback in [
            ("开始 / 继续", self.start_decode),
            ("暂停", self.pause_decode),
            ("停止并保存", self.pause_decode),
            ("取消任务", self.cancel_task),
            ("重新扫描视频", self.rescan),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        panel.addLayout(controls)
        self.status = QLabel("请打开工作区；单机模式无需 Token，无需另开终端。")
        self.status.setWordWrap(True)
        panel.addWidget(self.status)
        self.metrics = QLabel("总包数：等待 START")
        self.metrics.setWordWrap(True)
        panel.addWidget(self.metrics)
        panel.addWidget(QLabel("视频扫描进度（含重叠时间片）"))
        self.scan_bar = QProgressBar()
        panel.addWidget(self.scan_bar)
        panel.addWidget(QLabel("有效数据包完整率（不等于文件验证成功）"))
        self.packet_bar = QProgressBar()
        panel.addWidget(self.packet_bar)
        results = QHBoxLayout()
        for text, callback in [
            ("导出缺包 TXT / CSV / JSON", self.export_missing),
            ("校验并恢复文件", self.recover),
            ("打开结果目录", self.open_output),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            results.addWidget(button)
        panel.addLayout(results)
        self.tabs.addTab(main, "任务与恢复")
        node_panel = QWidget()
        node_layout = QVBoxLayout(node_panel)
        self.nodes = QTableWidget(0, 4)
        self.nodes.setHorizontalHeaderLabels(["唯一节点 ID", "状态", "处理中时间片", "最近心跳"])
        self.nodes.setColumnWidth(0, 400)
        self.nodes.horizontalHeader().setStretchLastSection(True)
        node_layout.addWidget(QLabel("节点状态（本机多个进程不代表真实双机验收）"))
        node_layout.addWidget(self.nodes)
        self.slice_table = QTableWidget(0, 5)
        self.slice_table.setHorizontalHeaderLabels(
            ["视频 / 时间片", "时间范围", "状态", "节点 / 尝试", "检查点 / 错误"]
        )
        self.slice_table.horizontalHeader().setStretchLastSection(True)
        node_layout.addWidget(QLabel("当前任务时间片；失败租约到期重领，已确认数据保留"))
        node_layout.addWidget(self.slice_table)
        self.tabs.addTab(node_panel, "节点与时间片")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(1000)
        self.tabs.addTab(self.log, "实时日志")
        layout.addWidget(self.tabs)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.setCentralWidget(scroll)
        self.setStyleSheet(
            "QWidget{font-family:'Microsoft YaHei UI';font-size:13px;} "
            "QPushButton{padding:7px 12px;border:1px solid #ccd6df;border-radius:5px;} "
            "QLineEdit,QComboBox{padding:5px;} QTabWidget::pane{border:1px solid #ccd6df;}"
            "QProgressBar{border:1px solid #ccd6df;border-radius:4px;background:#edf2f7;min-height:16px;text-align:center;}"
            "QProgressBar::chunk{background:#3178a8;border-radius:3px;}"
        )
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        QTimer.singleShot(0, self.connect_session)

    def submit(self, name, operation):
        if self.closing or (self.busy and name == "刷新"):
            return False
        self.pending_jobs += 1
        self.busy = True
        if name != "刷新":
            self.status.setText(f"正在执行：{name}…")
        self.job.jobs.put((name, operation))
        return True

    def task_id(self):
        return self.tasks.currentData()

    def select_task(self, *_):
        self.last_progress = {}
        self.output_path = None
        self.packet_bar.setValue(0)
        self.scan_bar.setValue(0)
        self.status.setText("已切换任务，正在读取已保存进度…")
        self.refresh()

    def connect_session(self):
        workspace = Path(self.workspace.text())
        server = self.server.text() if self.mode.currentIndex() else None
        token = self.token.text()

        def connect():
            if self.session:
                self.session.close()
            self.session = ManagedSession(workspace, server=server, token=token)
            return self.session.client.request("/tasks")

        self.submit("连接", connect)

    def choose_workspace(self):
        directory = QFileDialog.getExistingDirectory(self, "选择工作目录", self.workspace.text())
        if directory:
            self.workspace.setText(directory)

    def new_task(self):
        if not self.session or self.closing:
            return
        name, ok = QInputDialog.getText(
            self, "新建隔离任务", "任务名称（一个任务只能属于一个原文件）"
        )
        if not ok or not name:
            return
        self.create_task(name)

    def create_task(self, name):
        self.submit(
            "新建任务",
            lambda: self.session.client.request("/tasks", {"name": name, "protocol_version": 2}),
        )

    def choose_videos(self):
        if not self.task_id():
            QMessageBox.information(self, "先选择任务", "请先打开工作区并新建或选择原文件任务。")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加同一原文件录像", "", "视频 (*.mp4 *.avi *.mkv *.mov);;全部文件 (*)"
        )
        if paths and (
            QMessageBox.question(
                self,
                "确认来源",
                "这些录像是否都属于当前任务的同一个原文件？v2 DATA 无文件 ID，不能自动证明归属。",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.add_videos([Path(path) for path in paths])

    def add_videos(self, paths):
        task = self.task_id()
        slice_seconds = self.slice_seconds.value()
        if not self.session or not task:
            return

        def add():
            information = [inspect_video(path) for path in paths]
            existing = {v["path"] for v in self.session.client.request(f"/videos?task_id={task}")}
            for info in information:
                if info["path"] not in existing:
                    self.session.client.request(
                        "/videos",
                        {
                            "task_id": task,
                            "path": info["path"],
                            "duration_seconds": info["duration_seconds"],
                            "slice_seconds": slice_seconds,
                        },
                    )
                    existing.add(info["path"])
            return information

        self.submit("导入视频", add)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if (
            paths
            and self.task_id()
            and QMessageBox.question(self, "确认录像来源", "将所有拖入视频合并到当前原文件任务？")
            == QMessageBox.StandardButton.Yes
        ):
            self.add_videos(paths)

    def start_decode(self):
        task = self.task_id()
        count, fps = self.worker_count.value(), self.sample.value()
        if task:
            self.started_at = time.monotonic()
            self.submit("开始解码", lambda: self.session.start(task, count, fps))

    def pause_decode(self):
        task = self.task_id()
        if task:
            self.submit("暂停并保存", lambda: self.session.pause(task))

    def cancel_task(self):
        task = self.task_id()
        if task:
            self.submit("取消（数据保留，可继续）", lambda: self.session.cancel(task))

    def rescan(self):
        task = self.task_id()
        if task:

            def rescan():
                self.session.client.request(f"/tasks/{task}/resume", {})
                self.session.pause(task)
                for video in self.session.client.request(f"/videos?task_id={task}"):
                    self.session.client.request(f"/videos/{video['id']}/rescan", {})

            self.submit("重新扫描（已有包幂等保留）", rescan)

    def export_missing(self):
        task = self.task_id()
        if not task or self.last_progress.get("total_packets") is None:
            self.status.setText("等待 START：尚不能确定缺包，请先补充包含 START 的同任务录像。")
            return
        directory = QFileDialog.getExistingDirectory(self, "选择缺包导出目录（已有同名文件不覆盖）")
        if directory:

            def export():
                for extension in ("txt", "csv", "json"):
                    self.session.client.request(
                        f"/tasks/{task}/missing/download?format={extension}",
                        download=Path(directory) / f"missing.{extension}",
                    )
                return directory

            self.submit("导出缺包", export)

    def recover(self):
        task = self.task_id()
        if task and self.last_progress.get("recovery", {}).get("status") == "verified":
            self.status.setText("此任务已验证成功，已有文件不会覆盖；请打开结果目录。")
        elif task:
            self.submit("恢复", lambda: self.session.client.request(f"/tasks/{task}/recover", {}))

    def open_output(self):
        if self.output_path and Path(self.output_path).parent.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.output_path).parent)))
        else:
            self.status.setText("尚无可在本机打开的已验证结果；分布式文件位于控制机。")

    def refresh(self, *_):
        task = self.task_id()
        if not self.session or self.busy or self.closing:
            return

        def snapshot():
            client = self.session.client
            result = {"tasks": client.request("/tasks"), "nodes": client.request("/nodes")}
            result["worker_exits"] = [
                (p.pid, p.poll()) for p in self.session.workers if p.poll() is not None
            ]
            result["task_id"] = task
            if task:
                result.update(
                    progress=client.request(f"/tasks/{task}/progress"),
                    videos=client.request(f"/videos?task_id={task}"),
                )
                result["slices"] = [
                    s
                    for video in result["videos"]
                    for s in client.request(f"/slices?video_id={video['id']}")
                ]
                progress = result["progress"]
                if (
                    progress.get("total_packets") is not None
                    and not progress.get("cancelled")
                    and not progress.get("paused")
                    and progress["recovery"]["status"] == "not_started"
                    and result["slices"]
                    and all(s["state"] == "done" for s in result["slices"])
                ) or (
                    progress["recovery"]["status"] == "incomplete"
                    and progress.get("missing_count") == 0
                    and not progress.get("conflicts")
                    and not progress.get("paused")
                    and not progress.get("cancelled")
                ):
                    result["automatic_recovery"] = client.request(f"/tasks/{task}/recover", {})
            return result

        self.submit("刷新", snapshot)

    def done(self, name, result):
        self.pending_jobs = max(0, self.pending_jobs - 1)
        self.busy = bool(self.pending_jobs)
        if name == "关闭":
            self.job.jobs.put(None)
            self.job.wait(5000)
            self.close()
            return
        if name == "连接":
            self.settings.setValue("workspace", self.workspace.text())
            self.settings.setValue("server", self.server.text())
            self.tabs.setCurrentIndex(1)
            self.update_tasks(result)
            self.status.setText("工作区已打开，任务自动保存；请新建或选择已有原文件任务。")
        elif name == "新建任务":
            self.submit("连接任务列表", lambda: self.session.client.request("/tasks"))
            self.pending_task = result["id"]
        elif name == "连接任务列表":
            self.update_tasks(result, getattr(self, "pending_task", None))
        elif name == "刷新":
            self.update_tasks(result["tasks"])
            self.nodes.setRowCount(len(result["nodes"]))
            for row, node in enumerate(result["nodes"]):
                values = [
                    node["node_id"],
                    "在线" if node["status"] == "online" else "离线",
                    str(node["processing"]),
                    datetime.fromtimestamp(node["last_seen"]).strftime("%H:%M:%S"),
                ]
                for column, value in enumerate(values):
                    self.nodes.setItem(row, column, QTableWidgetItem(value))
            slices = result.get("slices", [])
            self.slice_table.setRowCount(len(slices))
            states = {
                "pending": "等待领取",
                "leased": "处理中",
                "done": "扫描完成",
                "cancelled": "已取消",
            }
            for row, item in enumerate(slices):
                values = [
                    f"{item['video_id']} / {item['id']}",
                    f"{item['start_ms'] / 1000:.1f}–{item['end_ms'] / 1000:.1f} 秒",
                    states.get(item["state"], item["state"]),
                    f"{item['owner'] or '-'} / {item['attempts']}",
                    item.get("error") or f"{item['checkpoint_ms'] / 1000:.1f} 秒",
                ]
                for column, value in enumerate(values):
                    self.slice_table.setItem(row, column, QTableWidgetItem(value))
            if "progress" in result and result["task_id"] == self.task_id():
                self.display_progress(result)
        elif name == "恢复":
            self.log.appendPlainText(json.dumps(result, ensure_ascii=False))
            self.status.setText(
                "恢复成功：哈希验证通过"
                if result["status"] == "verified"
                else "数据尚不完整，等待缺包补传"
            )
            self.output_path = result.get("path")
        else:
            self.status.setText(f"{name}完成；任务与已提交包自动保存。")
        self.read_logs()
        if self.closing:
            self.begin_close()

    def update_tasks(self, tasks, selected=None):
        selected = selected or self.task_id()
        self.tasks.blockSignals(True)
        self.tasks.clear()
        for task in tasks:
            self.tasks.addItem(f"#{task['id']} · {task['name']}", task["id"])
        index = self.tasks.findData(selected)
        if index >= 0:
            self.tasks.setCurrentIndex(index)
        self.tasks.blockSignals(False)

    def display_progress(self, result):
        progress = result["progress"]
        self.last_progress = progress
        total = progress["total_packets"]
        elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
        self.metrics.setText(
            f"总包数：{total if total is not None else '等待 START'}　已验证包：{progress['stored']}　缺包：{progress.get('missing_count', '待定')}　重复：{progress['duplicates']}　冲突：{progress['conflicts']}　耗时：{elapsed} 秒"
        )
        self.packet_bar.setValue(
            (100 if total == 0 else int(progress["stored"] / total * 100))
            if total is not None
            else 0
        )
        scan = progress["scan"]
        self.scan_bar.setValue(min(100, int(scan["scanned_ms"] / max(scan["total_ms"], 1) * 100)))
        recovery = result.get("automatic_recovery", progress["recovery"])
        self.output_path = recovery.get("path")
        state = "等待 START" if total is None else "处理中 / 待补传"
        if progress["conflicts"]:
            state = "数据包内容冲突：禁止恢复，请建立新的隔离任务并核对录像来源"
        elif progress["cancelled"]:
            state = "任务已取消；已提交数据保留，点击开始可继续"
        elif progress["paused"]:
            state = "已暂停 / 停止，数据已保存"
        elif recovery["status"] == "verified":
            state = f"恢复成功：数据完整且文件哈希匹配 · MD5 {recovery.get('md5', '')}"
        elif recovery["status"] == "failed":
            state = (
                f"恢复失败：请核对 MD5 / 来源 / 冲突，详情：{recovery.get('reason', '查看日志')}"
            )
        elif result.get("slices") and all(s["state"] == "done" for s in result["slices"]):
            state = "扫描完成，等待 START / 缺包补传；文件尚未恢复"
        self.status.setText(state)
        if result.get("worker_exits"):
            self.status.setText(
                f"本机 Worker 意外退出：{result['worker_exits']}；数据保留，请查看日志后继续。"
            )
        errors = [s["error"] for s in result["slices"] if s.get("error")]
        if errors and recovery["status"] != "verified":
            self.status.setText(f"时间片处理失败（未计为完成）：{errors[0]}")
        if "automatic_recovery" in result:
            self.log.appendPlainText(json.dumps(result["automatic_recovery"], ensure_ascii=False))
        self.videos.setRowCount(len(result["videos"]))
        for row, video in enumerate(result["videos"]):
            states = [s["state"] for s in result["slices"] if s["video_id"] == video["id"]]
            for column, value in enumerate(
                [
                    video["path"],
                    f"{video['duration_seconds']:.2f}",
                    f"{states.count('done')}/{len(states)} 时间片完成",
                ]
            ):
                self.videos.setItem(row, column, QTableWidgetItem(value))

    def read_logs(self):
        if not self.session:
            return
        for path in self.session.logs.glob("*.log"):
            with path.open("rb") as stream:
                stream.seek(self.log_offsets.get(path, 0))
                block = stream.read(65536)
                self.log_offsets[path] = stream.tell()
            if block:
                text = block.decode("utf-8", errors="replace").replace(
                    self.session.token, "[已隐藏]"
                )
                self.log.appendPlainText(f"[{path.name}]\n{text}")

    def failed(self, name, message):
        self.pending_jobs = max(0, self.pending_jobs - 1)
        self.busy = bool(self.pending_jobs)
        if self.session:
            message = message.replace(self.session.token, "[已隐藏]")
        self.status.setText(f"{name}失败：{message}；请查看实时日志。")
        self.log.appendPlainText(f"{name}失败：{message}")
        self.read_logs()
        if self.closing:
            self.begin_close()

    def begin_close(self):
        if self.busy:
            return
        self.busy = True
        self.pending_jobs += 1
        self.job.jobs.put(("关闭", lambda: self.session.close() if self.session else None))

    def closeEvent(self, event):
        if not self.job.isRunning():
            event.accept()
            return
        event.ignore()
        self.closing = True
        self.timer.stop()
        self.settings.setValue("sample_fps", self.sample.value())
        self.settings.setValue("workers", self.worker_count.value())
        self.settings.setValue("slice_seconds", self.slice_seconds.value())
        self.setEnabled(False)
        self.status.setText("正在停止本机进程并保存任务…")
        self.begin_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="QRFT v2 单机 / 分布式视频解码界面")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help="原生窗口启动后安全退出")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Microsoft YaHei UI", 10))
    smoke_settings = (
        QSettings(str(args.workspace / "smoke-settings.ini"), QSettings.Format.IniFormat)
        if args.smoke_test and args.workspace
        else None
    )
    window = DecoderWindow(args.workspace, settings=smoke_settings)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(1000, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

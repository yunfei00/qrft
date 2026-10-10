"""QRFT 第五个独立程序：图形化一键验收与无界面 CI 入口。"""

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qrft.acceptance.report import ITEMS, LABELS
from qrft.acceptance.runner import Runner


class Job(QThread):
    update = Signal(str, object)

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        runner.notify = self.update.emit

    def run(self):
        try:
            self.runner.execute()
        except Exception as exc:  # noqa: BLE001 - GUI thread must report unexpected failures
            self.update.emit("log", f"报告生成失败：{type(exc).__name__}: {exc}")


class AcceptanceWindow(QMainWindow):
    def __init__(self, programs=None):
        super().__init__()
        self.setWindowTitle("QRFT 一键验收")
        self.resize(920, 820)
        self.job = None
        self.report = None
        body = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(body)
        layout.addWidget(
            QLabel("使用独立测试目录。合成视频和本地双进程不等于真实双机 SMB 或录屏验收。")
        )
        form = QFormLayout()
        self.role = QComboBox()
        self.role.addItems(
            ["单机自动验收", "SMB 控制机 + Worker A", "SMB Worker B（另一台 Windows）"]
        )
        form.addRow("运行角色", self.role)
        self.smb_server = QLineEdit("http://控制机IP:8788")
        self.smb_share = QLineEdit()
        self.smb_share.setPlaceholderText(r"控制机：\\主机\共享目录；Worker B：完整 UNC 视频路径")
        self.smb_token = QLineEdit()
        self.smb_token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Worker B 控制中心地址", self.smb_server)
        form.addRow("SMB 路径", self.smb_share)
        form.addRow("双机共用 Token（不保存）", self.smb_token)

        def show_smb(index):
            for field in (self.smb_server, self.smb_share, self.smb_token):
                visible = index != 0 and (field is not self.smb_server or index == 2)
                field.setVisible(visible)
                form.labelForField(field).setVisible(visible)

        self.role.currentIndexChanged.connect(show_smb)
        show_smb(0)
        self.programs = QLineEdit(str(programs or Path(sys.executable).parent.parent))
        self.output = QLineEdit(str(Path.home() / "QRFT验收报告"))
        for title, field in (("完整程序目录", self.programs), ("结果保存目录", self.output)):
            row = QHBoxLayout()
            row.addWidget(field)
            choose = QPushButton("选择目录")
            choose.clicked.connect(lambda checked=False, field=field: self.choose(field))
            row.addWidget(choose)
            form.addRow(title, row)
        self.size = QComboBox()
        self.size.addItems(["10 MB", "100 MB", "1 GB", "自定义 MB"])
        self.custom = QSpinBox()
        self.custom.setRange(1, 10240)
        self.custom.setValue(10)
        self.custom.setVisible(False)
        self.size.currentIndexChanged.connect(lambda index: self.custom.setVisible(index == 3))
        size_row = QHBoxLayout()
        size_row.addWidget(self.size)
        size_row.addWidget(self.custom)
        form.addRow("大文件哈希性能（非二维码速度）", size_row)
        self.duration = QComboBox()
        self.duration.addItems(["10 分钟", "30 分钟", "60 分钟"])
        form.addRow("GUI 连续播放时长", self.duration)
        layout.addLayout(form)
        self.checks, self.states = {}, {}
        for key, title in ITEMS.items():
            row = QHBoxLayout()
            check = QCheckBox(title)
            check.setChecked(key not in ("smb", "performance", "qr_performance", "stability"))
            state = QLabel("未开始")
            row.addWidget(check)
            row.addStretch()
            row.addWidget(state)
            layout.addLayout(row)
            self.checks[key], self.states[key] = check, state
        actions = QHBoxLayout()
        self.start_button = QPushButton("开始验收")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("取消测试")
        self.cancel_button.clicked.connect(self.cancel)
        self.export_button = QPushButton("导出报告")
        self.export_button.clicked.connect(self.export)
        for button in (self.start_button, self.cancel_button, self.export_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(ITEMS))
        layout.addWidget(self.progress)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(2000)
        layout.addWidget(self.logs)

    def choose(self, field):
        path = QFileDialog.getExistingDirectory(self, "选择目录", field.text())
        if path:
            field.setText(path)

    def start(self):
        if self.job and self.job.isRunning():
            return
        try:
            size = [10, 100, 1024, self.custom.value()][self.size.currentIndex()] * 1024**2
            role = ["local", "controller", "worker"][self.role.currentIndex()]
            if role != "local" and not self.smb_token.text():
                raise ValueError("SMB 两端必须输入同一个 Token；不会写入配置或报告")
            selected = (
                [k for k, v in self.checks.items() if v.isChecked()] if role == "local" else ["smb"]
            )
            runner = Runner(
                Path(self.programs.text()),
                Path(self.output.text()),
                selected=selected,
                size_bytes=size,
                stability_seconds=[600, 1800, 3600][self.duration.currentIndex()],
                role=role,
                smb_server=self.smb_server.text(),
                smb_share=self.smb_share.text(),
                smb_video=self.smb_share.text(),
                smb_token=self.smb_token.text(),
            )
            self.job = Job(runner)
            self.job.update.connect(self.on_update)
            self.job.finished.connect(lambda: self.start_button.setEnabled(True))
            self.start_button.setEnabled(False)
            self.report = None
            self.logs.clear()
            self.progress.setValue(0)
            for state in self.states.values():
                state.setText("未开始")
            self.job.start()
        except (OSError, ValueError, RuntimeError) as exc:
            self.logs.append(str(exc))

    def on_update(self, kind, value):
        if kind == "result":
            self.states[value["id"]].setText(LABELS[value["status"]])
            self.progress.setValue(
                sum(label.text() not in ("未开始", "运行中") for label in self.states.values())
            )
        elif kind == "finished":
            self.report = Path(value)
            self.logs.append(f"报告已保存：{value}")
        else:
            self.logs.append(str(value))

    def cancel(self):
        if self.job:
            self.job.runner.cancel.set()

    def export(self):
        if not self.report:
            self.logs.append("请先完成验收；报告会自动保存。")
            return
        destination = QFileDialog.getExistingDirectory(self, "导出完整报告与证据")
        if destination:
            try:
                target = Path(destination) / ("QRFT报告-" + uuid.uuid4().hex)
                shutil.copytree(self.report.parent, target)
                self.logs.append(f"已导出：{target}")
            except OSError as exc:
                self.logs.append(str(exc))

    def closeEvent(self, event):
        if self.job and self.job.isRunning():
            self.cancel()
            self.logs.append("正在停止自有测试进程并保存报告，请稍候…")
            event.ignore()
            QTimer.singleShot(500, self.close)
            return
        super().closeEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description="QRFT 中文一键验收")
    parser.add_argument("--programs", type=Path)
    parser.add_argument("--output", type=Path, default=Path.home() / "QRFT验收报告")
    parser.add_argument("--headless", action="store_true", help="执行最小真实 EXE 验收并保存报告")
    parser.add_argument("--smoke-test", action="store_true", help="Qt 启动后自动退出")
    parser.add_argument(
        "--items", nargs="+", choices=list(ITEMS), help="无界面模式选择项目，默认完整软件验收"
    )
    parser.add_argument("--size-mb", type=int, default=10, help="哈希性能文件大小，1–10240 MiB")
    parser.add_argument(
        "--stability-seconds", type=int, default=600, help="GUI 播放时长，1–3600 秒"
    )
    args = parser.parse_args(argv)
    if not 1 <= args.size_mb <= 10240 or not 1 <= args.stability_seconds <= 3600:
        parser.error("size-mb or stability-seconds outside supported range")
    if args.items and not args.headless:
        parser.error("--items requires --headless")
    if args.headless:
        runner = Runner(
            args.programs or Path(sys.executable).parent.parent,
            args.output,
            selected=args.items
            or {
                "environment",
                "encoder",
                "decoder",
                "control",
                "single",
                "dual",
                "missing",
                "fault",
            },
            size_bytes=args.size_mb * 1024**2,
            stability_seconds=args.stability_seconds,
        )
        try:
            report = runner.execute()
            if args.items:
                if report["counts"]["failed"]:
                    return 1
                return (
                    0
                    if all(
                        r["status"] == "passed" for r in report["results"] if r["id"] in args.items
                    )
                    else 2
                )
            return 1 if report["counts"]["failed"] or not report["candidate_software_gate"] else 0
        except Exception as exc:  # noqa: BLE001 - frozen CLI preserves fatal diagnostics
            (runner.root / "fatal.json").write_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False), encoding="utf-8"
            )
            return 1
    app = QApplication.instance() or QApplication(sys.argv)
    window = AcceptanceWindow(args.programs)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(300, window.close)
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

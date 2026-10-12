"""QRFT 图形编码器：文件选择、参数配置、PNG 导出及实时播放。"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qrft.core.manifest import inspect_file
from qrft.encoder_cli.main import export_frames
from qrft.encoder_gui.player import PlayerWindow


class Job(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.operation(self.cancel.is_set))
        except (OSError, ValueError, RuntimeError) as exc:
            self.failed.emit(str(exc))


class EncoderWindow(QMainWindow):
    """与 CLI 共享编码核心的 Windows 图形入口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("QRFT 图形编码器")
        self.resize(760, 620)
        self.jobs = []
        self.player = None
        root = QWidget(self)
        layout = QVBoxLayout(root)
        form = QFormLayout()
        self.protocol = QComboBox()
        self.protocol.addItems(["v1 原始字节 + CRC32", "v2 HEX + MD5"])
        form.addRow("二维码协议", self.protocol)
        self.source = QLineEdit()
        self.source.setPlaceholderText("选择任意二进制文件")
        source_row = QHBoxLayout()
        source_row.addWidget(self.source)
        browse = QPushButton("选择文件")
        browse.clicked.connect(self.choose_source)
        source_row.addWidget(browse)
        form.addRow("源文件", source_row)
        self.output = QLineEdit()
        self.output.setPlaceholderText("导出 PNG 的目标文件夹")
        output_row = QHBoxLayout()
        output_row.addWidget(self.output)
        browse_output = QPushButton("选择目录")
        browse_output.clicked.connect(self.choose_output)
        output_row.addWidget(browse_output)
        form.addRow("导出目录", output_row)
        self.retransmit = QLineEdit()
        self.retransmit.setPlaceholderText("可选：missing.txt 缺包清单")
        missing_row = QHBoxLayout()
        missing_row.addWidget(self.retransmit)
        browse_missing = QPushButton("选择缺包清单")
        browse_missing.clicked.connect(self.choose_missing)
        missing_row.addWidget(browse_missing)
        form.addRow("补传清单", missing_row)
        self.chunk_size = QSpinBox()
        self.chunk_size.setRange(1, 4096)
        self.chunk_size.setValue(256)
        form.addRow("每包字节数", self.chunk_size)
        self.interval_ms = QSpinBox()
        self.interval_ms.setRange(1, 60000)
        self.interval_ms.setValue(300)
        form.addRow("播放间隔（毫秒）", self.interval_ms)
        self.delay_ms = QSpinBox()
        self.delay_ms.setRange(0, 60000)
        self.delay_ms.setValue(3000)
        form.addRow("开始延迟（毫秒）", self.delay_ms)
        self.start_id = QSpinBox()
        self.start_id.setRange(0, 88888887)
        self.end_id = QSpinBox()
        self.end_id.setRange(-1, 88888887)
        self.end_id.setValue(-1)
        self.end_id.setSpecialValueText("末包")
        range_row = QHBoxLayout()
        range_row.addWidget(self.start_id)
        range_row.addWidget(QLabel("至"))
        range_row.addWidget(self.end_id)
        form.addRow("数据包范围", range_row)
        self.correction = QComboBox()
        self.correction.addItems(["M", "L", "Q", "H"])
        self.box_size = QSpinBox()
        self.box_size.setRange(2, 16)
        self.box_size.setValue(8)
        self.protocol.currentIndexChanged.connect(self.change_protocol)
        qr_row = QHBoxLayout()
        qr_row.addWidget(QLabel("纠错"))
        qr_row.addWidget(self.correction)
        qr_row.addWidget(QLabel("像素 / 模块"))
        qr_row.addWidget(self.box_size)
        form.addRow("二维码参数", qr_row)
        self.fullscreen = QCheckBox("开始时全屏播放（F11 可切换）")
        self.fullscreen.setChecked(True)
        form.addRow(self.fullscreen)
        layout.addLayout(form)
        self.metadata = QLabel("文件信息：选择文件后点击检查；哈希计算在后台运行。")
        self.metadata.setWordWrap(True)
        self.metadata.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.metadata)
        actions = QHBoxLayout()
        inspect = QPushButton("检查文件")
        inspect.clicked.connect(self.inspect_source)
        actions.addWidget(inspect)
        export = QPushButton("导出二维码 PNG")
        export.clicked.connect(self.export_png)
        actions.addWidget(export)
        playback = QPushButton("开始播放")
        playback.clicked.connect(self.start_playback)
        actions.addWidget(playback)
        pause = QPushButton("暂停 / 继续")
        pause.clicked.connect(lambda: self.player.toggle_pause() if self.player else None)
        actions.addWidget(pause)
        stop = QPushButton("停止")
        stop.clicked.connect(self.stop_jobs)
        actions.addWidget(stop)
        layout.addLayout(actions)
        self.status = QLabel("就绪。播放时按空格暂停或继续，按 Esc 退出。")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def choose_source(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "选择源文件")
        if name:
            self.source.setText(name)
            self.inspect_source()

    def change_protocol(self, index):
        v2 = index == 1
        self.chunk_size.setValue(1400 if v2 else 256)
        self.interval_ms.setValue(50 if v2 else 300)
        self.correction.setCurrentText("L" if v2 else "M")
        self.box_size.setValue(10 if v2 else 8)
        for control in (self.chunk_size, self.interval_ms, self.correction, self.box_size):
            control.setEnabled(not v2)
        self.status.setText(
            "v2 固定1400字节、L/10/4、50%图像；START/FINISH各20次" if v2 else "v1 参数可配置"
        )

    def choose_output(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if name:
            self.output.setText(name)

    def choose_missing(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "选择缺包清单", filter="文本文件 (*.txt);;所有文件 (*)"
        )
        if name:
            self.retransmit.setText(name)

    def paths(self) -> tuple[Path, Path | None]:
        source = Path(self.source.text().strip())
        if not source.is_file():
            raise ValueError("请选择存在的源文件")
        missing = Path(self.retransmit.text().strip()) if self.retransmit.text().strip() else None
        if missing is not None and not missing.is_file():
            raise ValueError("缺包清单文件不存在")
        return source, missing

    def export_png(self) -> None:
        try:
            source, missing = self.paths()
            if not self.output.text().strip():
                raise ValueError("请选择导出目录")
            output = Path(self.output.text().strip())
            options = self.options(missing)
            self.start_job(
                lambda cancelled: export_frames(source, output, cancelled=cancelled, **options),
                lambda result: self.status.setText(
                    f"导出完成：{result['exported_data_packets']} 个数据包"
                ),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def start_playback(self) -> None:
        try:
            source, missing = self.paths()
            if self.player and not self.player.finished:
                raise ValueError("已有播放任务，请先停止")
            self.player = PlayerWindow(
                source,
                interval_ms=self.interval_ms.value(),
                initial_delay_ms=self.delay_ms.value(),
                fullscreen=self.fullscreen.isChecked(),
                **self.options(missing),
            )
            self.player.progress.connect(
                lambda packet, count: self.status.setText(f"播放中：{packet}，已显示 {count} 帧")
            )
            self.player.stopped.connect(lambda: self.status.setText("播放已停止或完成"))
            self.player.show()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "播放失败", str(exc))

    def options(self, missing):
        return {
            "protocol_version": 2 if self.protocol.currentIndex() == 1 else 1,
            "chunk_size": self.chunk_size.value(),
            "retransmit": missing,
            "start_id": self.start_id.value(),
            "end_id": None if self.end_id.value() == -1 else self.end_id.value(),
            "qr_options": {
                "correction": self.correction.currentText(),
                "box_size": self.box_size.value(),
            },
        }

    def start_job(self, operation, finished):
        if any(job.isRunning() for job in self.jobs):
            raise ValueError("后台任务正在执行，请稍候或停止")
        job = Job(operation, self)
        self.jobs.append(job)
        job.result.connect(finished)
        job.failed.connect(lambda message: self.status.setText(f"任务失败：{message}"))
        job.finished.connect(lambda: self.jobs.remove(job))
        self.status.setText("后台处理中…")
        job.start()

    def inspect_source(self):
        try:
            source, _ = self.paths()
            chunk = self.chunk_size.value()

            def display(meta):
                self.metadata.setText(
                    f"{meta['filename']} · {meta['file_size']:,} 字节 · {meta['total_packets']:,} 包\n"
                    f"SHA256 {meta['sha256']}\nMD5 {meta['md5']}"
                )

            self.start_job(
                lambda cancelled: inspect_file(source, chunk, cancelled=cancelled), display
            )
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))

    def stop_jobs(self):
        for job in self.jobs:
            job.cancel.set()
        if self.player:
            self.player.close()

    def closeEvent(self, event):
        self.stop_jobs()
        for job in list(self.jobs):
            job.wait()
        super().closeEvent(event)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="QRFT Encoder GUI")
    parser.add_argument(
        "--smoke-test", action="store_true", help="start Qt window and exit automatically"
    )
    parser.add_argument("--stability-file", type=Path, help="验收：连续播放指定测试文件")
    parser.add_argument("--stability-seconds", type=int, default=600)
    parser.add_argument("--stability-evidence", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.stability_seconds <= 3600:
        parser.error("stability-seconds must be between 1 and 3600")
    app = QApplication.instance() or QApplication(sys.argv)
    window = EncoderWindow()
    window.show()
    evidence = {"displayed_frames": 0, "completed_cycles": 0, "error": None}
    started = time.perf_counter()
    if args.stability_file:
        if not args.stability_file.is_file():
            parser.error("stability-file does not exist")

        def progress(*args):
            evidence["displayed_frames"] += 1

        def replay():
            window.player = PlayerWindow(
                args.stability_file, interval_ms=100, initial_delay_ms=0, fullscreen=False
            )
            window.player.show()
            window.player.progress.connect(progress)

        replay()
        repeat = QTimer(window)

        def check_playback():
            if time.perf_counter() - started >= args.stability_seconds:
                repeat.stop()
                window.close()
                app.quit()
                return
            if window.player.finished:
                if window.player.error:
                    evidence["error"] = window.player.error
                    repeat.stop()
                    window.close()
                    app.exit(1)
                    return
                evidence["completed_cycles"] += 1
                window.player.close()
                replay()

        repeat.timeout.connect(check_playback)
        repeat.start(200)
    if args.smoke_test:
        QTimer.singleShot(300, window.close)
        QTimer.singleShot(500, app.quit)
    code = app.exec()
    if args.stability_file and args.stability_evidence:
        evidence["elapsed_seconds"] = time.perf_counter() - started
        evidence["qt_platform"] = app.platformName()
        with args.stability_evidence.open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

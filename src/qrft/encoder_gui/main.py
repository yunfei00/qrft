"""QRFT 图形编码器：文件选择、参数配置、PNG 导出及实时播放。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
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

from qrft.encoder_cli.main import export_frames
from qrft.encoder_cli.player import play


class EncoderWindow(QMainWindow):
    """与 CLI 共享编码核心的 Windows 图形入口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("QRFT 图形编码器")
        self.resize(660, 340)
        root = QWidget(self)
        layout = QVBoxLayout(root)
        form = QFormLayout()
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
        layout.addLayout(form)
        actions = QHBoxLayout()
        export = QPushButton("导出二维码 PNG")
        export.clicked.connect(self.export_png)
        actions.addWidget(export)
        playback = QPushButton("全屏播放二维码")
        playback.clicked.connect(self.start_playback)
        actions.addWidget(playback)
        layout.addLayout(actions)
        self.status = QLabel("就绪。播放时按空格暂停或继续，按 Esc 退出。")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def choose_source(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "选择源文件")
        if name:
            self.source.setText(name)

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
            QApplication.setOverrideCursor(
                __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CursorShape.WaitCursor
            )
            try:
                result = export_frames(
                    source,
                    Path(self.output.text().strip()),
                    chunk_size=self.chunk_size.value(),
                    retransmit=missing,
                )
            finally:
                QApplication.restoreOverrideCursor()
            self.status.setText(f"导出完成：{result['exported_data_packets']} 个数据包")
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def start_playback(self) -> None:
        try:
            source, missing = self.paths()
            play(
                source,
                chunk_size=self.chunk_size.value(),
                interval_ms=self.interval_ms.value(),
                initial_delay_ms=self.delay_ms.value(),
                retransmit=missing,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "播放失败", str(exc))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = EncoderWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared nonblocking Qt player with bounded background PNG generation."""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from qrft.core.manifest import selected_ranges
from qrft.core.protocol import decode_frame
from qrft.encoder_cli.playback import iter_encoded_frames
from qrft.encoder_cli.prefetch import prefetch_png


class PlayerWindow(QWidget):
    progress = Signal(str, int)
    stopped = Signal()

    def __init__(
        self,
        source: Path,
        *,
        interval_ms=300,
        initial_delay_ms=3000,
        fullscreen=True,
        workers=2,
        prefetch=4,
        qr_options=None,
        exit_when_finished=False,
        **options,
    ):
        super().__init__()
        if interval_ms < 1 or initial_delay_ms < 0 or not 1 <= workers <= prefetch:
            raise ValueError("invalid playback timing/cache settings")
        self.setWindowTitle("QRFT 二维码播放")
        self.resize(900, 900)
        self.exit_when_finished = exit_when_finished
        self.setStyleSheet("background:white;color:black")
        layout = QVBoxLayout(self)
        self.image = QLabel("准备二维码…")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image, 1)
        self.status = QLabel("准备中，空格暂停/继续，F11 全屏，Esc 退出全屏或停止")
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        buttons = QHBoxLayout()
        self.pause_button = QPushButton("暂停")
        self.pause_button.clicked.connect(self.toggle_pause)
        buttons.addWidget(self.pause_button)
        full = QPushButton("全屏 / 窗口")
        full.clicked.connect(self.toggle_fullscreen)
        buttons.addWidget(full)
        stop = QPushButton("停止")
        stop.clicked.connect(self.close)
        buttons.addWidget(stop)
        layout.addLayout(buttons)
        self.paused = False
        self.finished = False
        self.displayed = 0
        self.interval = interval_ms / 1000
        self.deadline = time.monotonic() + initial_delay_ms / 1000
        self.stop_event = threading.Event()
        self.pending = queue.Queue(maxsize=prefetch)
        self.pixmap = QPixmap()

        def produce():
            prepared = prefetch_png(
                iter_encoded_frames(source, cancelled=self.stop_event.is_set, **options),
                workers=workers,
                capacity=prefetch,
                qr_options=qr_options,
            )
            try:
                for item in prepared:
                    if item[0][0] == "START":
                        meta = decode_frame(item[0][1]).metadata
                        count = sum(
                            last - first + 1
                            for first, last in selected_ranges(
                                meta["total_packets"],
                                start_id=options.get("start_id", 0),
                                end_id=options.get("end_id"),
                                retransmit=options.get("retransmit"),
                                cancelled=self.stop_event.is_set,
                            )
                        )
                        if not put({"selected": count + 2}):
                            return
                    if not put(item):
                        return
                put(None)
            except (OSError, ValueError, RuntimeError) as exc:
                put(exc)
            finally:
                prepared.close()

        def put(item):
            while not self.stop_event.is_set():
                try:
                    self.pending.put(item, timeout=0.05)
                    return True
                except queue.Full:
                    continue
            return False

        self.thread = threading.Thread(target=produce, name="qrft-png", daemon=True)
        self.thread.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(20)
        if fullscreen:
            self.showFullScreen()

    def toggle_pause(self):
        if self.finished:
            return
        self.paused = not self.paused
        self.pause_button.setText("继续" if self.paused else "暂停")
        if not self.paused:
            self.deadline = time.monotonic()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def advance(self):
        if self.finished or self.paused or time.monotonic() < self.deadline:
            return
        try:
            item = self.pending.get_nowait()
        except queue.Empty:
            return
        if isinstance(item, dict):
            self.bar.setRange(0, item["selected"])
            return
        if item is None or isinstance(item, BaseException):
            self.finished = True
            self.timer.stop()
            self.status.setText("播放完成" if item is None else f"播放失败：{item}")
            self.bar.setRange(0, 100)
            self.bar.setValue(100 if item is None else 0)
            self.stopped.emit()
            if self.exit_when_finished and item is None:
                self.close()
            return
        (packet_id, _raw), png = item
        if not self.pixmap.loadFromData(png, "PNG"):
            self.status.setText("二维码图像加载失败")
            self.close()
            return
        self.displayed += 1
        self.bar.setValue(self.displayed)
        remaining = max(0, self.bar.maximum() - self.displayed) * self.interval
        self.status.setText(
            f"当前 {packet_id} · 已播放 {self.displayed} 帧 · 预计剩余 {remaining:.0f} 秒"
        )
        self.progress.emit(packet_id, self.displayed)
        self.render()
        self.deadline = time.monotonic() + self.interval

    def render(self):
        if not self.pixmap.isNull():
            self.image.setPixmap(
                self.pixmap.scaled(
                    self.image.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )

    def resizeEvent(self, event):
        self.render()
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_pause()
        elif event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape:
            self.showNormal() if self.isFullScreen() else self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.stop_event.set()
        self.timer.stop()
        self.thread.join()
        self.finished = True
        self.stopped.emit()
        super().closeEvent(event)

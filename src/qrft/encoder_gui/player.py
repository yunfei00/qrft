"""Shared nonblocking Qt player with bounded background PNG generation."""

from __future__ import annotations

import math
import queue
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from qrft.core.manifest import selected_ranges
from qrft.core.protocol import decode_frame
from qrft.encoder_cli.playback import iter_encoded_frames
from qrft.encoder_cli.prefetch import prefetch_png
from qrft.encoder_cli.recording import QR_SIDE


class PlayerWindow(QWidget):
    progress = Signal(str, int)
    stopped = Signal()
    state_changed = Signal(str)

    def __init__(
        self,
        source: Path,
        *,
        interval_ms=300,
        initial_delay_ms=3000,
        fullscreen=False,
        workers=2,
        prefetch=4,
        qr_options=None,
        exit_when_finished=False,
        protocol_version=1,
        **options,
    ):
        super().__init__()
        if interval_ms < 1 or initial_delay_ms < 0 or not 1 <= workers <= prefetch:
            raise ValueError("invalid playback timing/cache settings")
        self.setWindowTitle("QRFT 二维码播放")
        ratio = self.devicePixelRatioF()
        self.qr_side = math.ceil(QR_SIDE / ratio)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(8, round(12 / ratio)))
        self.setFont(font)
        self.setFixedSize(math.ceil(946 / ratio), math.ceil(1002 / ratio))
        area = self.screen().geometry() if fullscreen else self.screen().availableGeometry()
        if QGuiApplication.platformName() != "offscreen" and (
            self.width() > area.width() or self.height() + (0 if fullscreen else 32) > area.height()
        ):
            raise ValueError("屏幕空间不足，无法完整显示固定录屏区；请使用更大屏幕或预选全屏")
        self.move(area.x() + max(0, (area.width() - self.width()) // 2), area.y())
        self.exit_when_finished = exit_when_finished
        self.protocol_version = protocol_version
        self.setStyleSheet("background:#edf1f7;color:#22324a")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(math.ceil(10 / ratio), 0, math.ceil(10 / ratio), 0)
        layout.setSpacing(0)
        caption = QLabel("录屏区域：下方固定白色正方形（含二维码静区）")
        caption.setFixedHeight(math.ceil(24 / ratio))
        layout.addWidget(caption)
        self.image = QLabel("准备二维码…")
        self.image.setStyleSheet("background:white;color:black")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedSize(self.qr_side, self.qr_side)
        layout.addWidget(self.image, 0, Qt.AlignmentFlag.AlignHCenter)
        self.status = QLabel("准备首帧；Space 开始/暂停/继续，Esc 停止")
        self.status.setFixedHeight(math.ceil(20 / ratio))
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(math.ceil(4 / ratio))
        layout.addWidget(self.bar)
        buttons = QHBoxLayout()
        self.pause_button = QPushButton("开始（Space）")
        self.pause_button.clicked.connect(self.toggle_pause)
        buttons.addWidget(self.pause_button)
        full = QPushButton("全屏 / 窗口")
        full.clicked.connect(self.toggle_fullscreen)
        buttons.addWidget(full)
        stop = QPushButton("停止")
        stop.clicked.connect(self.close)
        buttons.addWidget(stop)
        layout.addLayout(buttons)
        for button in (self.pause_button, full, stop):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setFixedHeight(math.ceil(28 / ratio))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.paused = True
        self.ready = False
        self.started = False
        self.finished = False
        self.error = None
        self.displayed = 0
        self.interval = interval_ms / 1000
        self.deadline = float("inf")
        self.stop_event = threading.Event()
        self.pending = queue.Queue(maxsize=prefetch)
        self.pixmap = QPixmap()
        announced = False

        def produce():
            nonlocal announced
            prepared = prefetch_png(
                iter_encoded_frames(
                    source,
                    cancelled=self.stop_event.is_set,
                    protocol_version=protocol_version,
                    **options,
                ),
                workers=workers,
                capacity=prefetch,
                qr_options=qr_options,
                protocol_version=protocol_version,
            )
            try:
                for item in prepared:
                    if item[0][0] == "START" and not announced:
                        announced = True
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
                        if not put({"selected": count + (40 if protocol_version == 2 else 2)}):
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
        self.timer.start(5 if protocol_version == 2 else 20)
        if fullscreen:
            self.showFullScreen()

    def toggle_pause(self):
        if self.finished or not self.ready:
            return
        self.started = True
        self.paused = not self.paused
        self.pause_button.setText("继续" if self.paused else "暂停")
        if not self.paused:
            self.deadline = time.monotonic() + self.frame_interval
        self.status.setText("已暂停；Space 继续" if self.paused else "播放中；Space 暂停")
        self.state_changed.emit(self.status.text())

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def advance(self):
        if self.finished or (self.ready and (self.paused or time.monotonic() < self.deadline)):
            return
        try:
            item = self.pending.get_nowait()
        except queue.Empty:
            return
        if isinstance(item, dict):
            self.bar.setRange(0, item["selected"])
            return
        if item is None or isinstance(item, BaseException):
            self.error = str(item) if isinstance(item, BaseException) else None
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
            self.error = "二维码图像加载失败"
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
        self.frame_interval = (
            0.05
            if self.protocol_version == 2 and packet_id in ("START", "FINISH")
            else self.interval
        )
        self.deadline = time.monotonic() + self.frame_interval
        if not self.ready:
            self.ready = True
            self.status.setText("首帧已就绪，静止等待；Space 开始，Esc 停止")
            self.state_changed.emit(self.status.text())

    def render(self):
        if not self.pixmap.isNull():
            if self.protocol_version == 2:
                ratio = self.devicePixelRatioF()
                self.pixmap.setDevicePixelRatio(ratio)
                if (
                    self.image.width() * ratio < self.pixmap.width()
                    or self.image.height() * ratio < self.pixmap.height()
                ):
                    self.error = "窗口空间不足；请全屏或增大窗口，二维码不能裁切"
                    self.status.setText(self.error)
                    self.timer.stop()
                    self.finished = True
                    self.stopped.emit()
                    if self.exit_when_finished:
                        QTimer.singleShot(0, self.close)
                    return
                self.image.setPixmap(self.pixmap)
                return
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
        if event.isAutoRepeat():
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space:
            self.toggle_pause()
        elif event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.stop_event.set()
        self.timer.stop()
        self.thread.join()
        self.finished = True
        self.stopped.emit()
        super().closeEvent(event)

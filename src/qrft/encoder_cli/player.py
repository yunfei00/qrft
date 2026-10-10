"""Windows 全屏二维码播放器：空格暂停、Esc 停止。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

from qrft.core.qr_image import qr_png
from qrft.encoder_cli.playback import iter_encoded_frames


def play(
    source: Path,
    *,
    chunk_size: int = 256,
    interval_ms: int = 300,
    initial_delay_ms: int = 3000,
    retransmit: Path | None = None,
    fullscreen: bool = True,
) -> int:
    """延迟启动并按定时器显示二维码，数据帧在播放时才生成。"""
    if interval_ms < 1 or initial_delay_ms < 0:
        raise ValueError("invalid interval or initial delay")

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QLabel

    frames: Iterator[tuple[str, bytes]] = iter_encoded_frames(
        source, chunk_size=chunk_size, retransmit=retransmit
    )
    app = QApplication.instance() or QApplication(sys.argv)

    class Player(QLabel):
        def __init__(self) -> None:
            super().__init__("QRFT 准备播放，空格暂停 / 继续，Esc 退出")
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setStyleSheet("background: white; color: black; font-size: 24px;")
            self.timer = QTimer(self)
            self.timer.setInterval(interval_ms)
            self.timer.timeout.connect(self.advance)
            self.paused = False
            QTimer.singleShot(initial_delay_ms, self.advance)

        def advance(self) -> None:
            if self.paused:
                return
            try:
                packet_id, frame = next(frames)
            except StopIteration:
                self.timer.stop()
                self.setText("QRFT 播放完成，按 Esc 退出")
                return
            image = QPixmap()
            if not image.loadFromData(qr_png(frame), "PNG"):
                self.timer.stop()
                self.setText(f"二维码生成失败：{packet_id}")
                return
            self.setPixmap(
                image.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )
            self.timer.start()

        def keyPressEvent(self, event: object) -> None:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close()
            elif key == Qt.Key.Key_Space:
                self.paused = not self.paused
                if self.paused:
                    self.timer.stop()
                else:
                    self.timer.start()
            else:
                super().keyPressEvent(event)

    window = Player()
    if fullscreen:
        window.showFullScreen()
    else:
        window.resize(900, 900)
        window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 全屏实时二维码播放器")
    parser.add_argument("source", type=Path)
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--interval-ms", type=int, default=300)
    parser.add_argument("--initial-delay-ms", type=int, default=3000)
    parser.add_argument("--retransmit", type=Path)
    parser.add_argument("--windowed", action="store_true")
    args = parser.parse_args(argv)
    return play(
        args.source,
        chunk_size=args.chunk_size,
        interval_ms=args.interval_ms,
        initial_delay_ms=args.initial_delay_ms,
        retransmit=args.retransmit,
        fullscreen=not args.windowed,
    )


if __name__ == "__main__":
    raise SystemExit(main())

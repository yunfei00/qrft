"""Isolated Qt application lifecycle, with real MP4 and managed source workers."""

import sys
import time
from pathlib import Path

from test_decoder_desktop import mp4

from qrft.encoder_cli.playback import iter_encoded_frames


def exercise_gui(tmp_path):
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from qrft.decoder_gui.main import DecoderWindow

    app = QApplication.instance() or QApplication([])
    source = tmp_path / "桌面.bin"
    source.write_bytes(bytes(range(256)))
    video = mp4(iter_encoded_frames(source, protocol_version=2), tmp_path / "desktop.mp4")
    window = DecoderWindow(
        tmp_path / "workspace",
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    window.timer.setInterval(100)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)

    def until(condition, timeout=40):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            QTest.qWait(10)
        raise AssertionError(
            f"{window.status.text()}\nWorker states: {[(p.args, p.poll()) for p in window.session.workers]}"
        )

    try:
        window.show()
        until(lambda: window.session is not None and not window.busy)
        window.timer.stop()
        window.create_task("GUI real MP4")
        until(lambda: window.task_id() is not None and not window.busy)
        window.add_videos([video])
        until(lambda: not window.busy)
        window.start_decode()
        until(lambda: not window.busy)
        window.timer.start(100)
        until(lambda: "恢复成功" in window.status.text())
        assert Path(window.output_path).read_bytes() == source.read_bytes()
        assert len(ticks) > 20  # event loop kept running during real decoding
        window.timer.stop()
        until(lambda: not window.busy)
        window.pause_decode()
        until(lambda: not window.busy)
        window.refresh()
        until(lambda: not window.busy)
        assert window.last_progress["paused"]
        window.cancel_task()
        until(lambda: not window.busy)
        window.refresh()
        until(lambda: not window.busy)
        assert window.last_progress["cancelled"]
        window.close()
        until(lambda: not window.job.isRunning())
    finally:
        timer.stop()
        window.close()
        until(lambda: not window.job.isRunning())


if __name__ == "__main__":
    exercise_gui(Path(sys.argv[1]))

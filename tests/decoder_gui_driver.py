"""Isolated Qt application lifecycle, with real MP4 and managed source workers."""

import sys
import threading
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
            f"{window.status.text()}\n"
            f"Worker states: {[(p.args, p.poll()) for p in window.session.workers]}\n"
            f"Pending GUI jobs: {window.pending_jobs}; background thread: {window.job.isRunning()}\n"
            f"GUI log:\n{window.log.toPlainText()[-12000:]}"
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


def exercise_busy_dialog(tmp_path):
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QDialogButtonBox,
        QInputDialog,
        QLineEdit,
        QPushButton,
    )

    from qrft.decoder_gui.main import DecoderWindow

    app = QApplication.instance() or QApplication([])
    window = DecoderWindow(
        tmp_path / "workspace",
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    gate, entered, dialogs = threading.Event(), threading.Event(), []
    timer = QTimer()

    def until(condition):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            QTest.qWait(10)
        raise AssertionError(window.status.text())

    def answer():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QInputDialog) or dialog.windowTitle() in dialogs:
            return
        dialogs.append(dialog.windowTitle())
        edit = dialog.findChild(QLineEdit)
        if edit is not None:
            QTest.keyClicks(edit, "Busy refresh regression")
            QTest.keyClick(edit, Qt.Key.Key_Return)
        else:
            box = dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(
                box.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton
            )

    try:
        window.show()
        until(lambda: window.session is not None and not window.busy)
        window.timer.stop()
        window.tabs.setCurrentIndex(1)
        app.processEvents()
        original = window.session.client.request

        def delayed(route, *args, **kwargs):
            if route == "/tasks" and not gate.is_set():
                entered.set()
                assert gate.wait(10)
            return original(route, *args, **kwargs)

        window.session.client.request = delayed
        window.refresh()
        until(entered.is_set)
        assert window.busy
        timer.timeout.connect(answer)
        timer.start(20)
        button = next(b for b in window.findChildren(QPushButton) if b.text() == "新建任务")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert dialogs == ["新建隔离任务"], "new-task click lost during real background refresh"
        gate.set()
        until(lambda: not window.busy and window.task_id() is not None)
        assert "Busy refresh regression" in window.tasks.currentText()
    finally:
        timer.stop()
        gate.set()
        window.close()
        until(lambda: not window.job.isRunning())


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "busy-dialog":
        exercise_busy_dialog(Path(sys.argv[1]))
    else:
        exercise_gui(Path(sys.argv[1]))

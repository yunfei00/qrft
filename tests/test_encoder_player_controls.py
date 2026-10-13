"""Real QR images/Qt events; mock only OpenCV desktop key and window I/O."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qrft.encoder_cli import opencv_player
from qrft.encoder_cli.recording import HEADER, PADDING, QR_SIDE, KeyLatch, recording_canvas
from qrft.encoder_gui.main import EncoderWindow
from qrft.encoder_gui.player import PlayerWindow


def ready(app, window):
    deadline = time.monotonic() + 10
    while not window.ready and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    assert window.ready and not window.error


def test_qt_first_frame_space_repeat_pause_resume_escape_and_geometry(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "文件.bin"
    source.write_bytes(bytes(range(256)) * 7)
    missing = tmp_path / "missing.txt"
    missing.write_text("00000001\n")
    positions = []
    for selection in (None, missing):
        window = PlayerWindow(source, protocol_version=2, retransmit=selection)
        try:
            window.show()
            ready(app, window)
            assert not window.isFullScreen() and window.paused and not window.started
            positions.append((window.size(), window.image.geometry()))
            count = window.displayed
            QTest.qWait(120)
            app.processEvents()
            assert window.displayed == count == 1
            QTest.keyClick(window, Qt.Key.Key_Space)
            assert not window.paused and window.started
            repeated = QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ", True, 1
            )
            app.sendEvent(window, repeated)
            assert not window.paused
            QTest.keyClick(window, Qt.Key.Key_Space)
            assert window.paused
            paused = window.displayed
            QTest.qWait(120)
            app.processEvents()
            assert window.displayed == paused
            QTest.keyClick(window, Qt.Key.Key_Space)
            assert not window.paused
            QTest.qWait(120)
            app.processEvents()
            assert window.displayed > paused
            assert window.image.geometry() == positions[-1][1]
            QTest.keyClick(window, Qt.Key.Key_Escape)
            assert window.finished and not window.thread.is_alive()
        finally:
            window.close()
    assert positions[0] == positions[1]


def test_gui_has_no_console_gate_and_windowed_default(tmp_path, monkeypatch):
    from qrft.encoder_cli import entrypoint

    monkeypatch.setattr(entrypoint, "authenticate", lambda: pytest.fail("GUI used CLI gate"))
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "gui.bin"
    source.write_bytes(b"data")
    gui = EncoderWindow()
    try:
        gui.source.setText(str(source))
        gui.protocol.setCurrentIndex(1)
        assert not gui.fullscreen.isChecked()
        assert gui.chunk_size.value() == 1400 and not gui.chunk_size.isEnabled()
        gui.start_playback()
        ready(app, gui.player)
        assert gui.player.paused and not gui.player.started
    finally:
        gui.close()


def test_recording_region_never_contains_status_or_border():
    image = np.full((125, 125, 3), 255, np.uint8)
    image[20:105, 20:105] = 0
    first = recording_canvas(image, "START", "READY")
    second = recording_canvas(image, "00000000", "PLAYING")
    region = (slice(HEADER, HEADER + QR_SIDE), slice(PADDING, PADDING + QR_SIDE))
    assert np.array_equal(first[region], second[region])
    y = HEADER + (QR_SIDE - 125) // 2
    x = PADDING + (QR_SIDE - 125) // 2
    assert np.array_equal(first[y : y + 125, x : x + 125], image)
    assert np.all(first[HEADER : HEADER + 10, PADDING : PADDING + QR_SIDE] == 255)


def test_space_latch_suppresses_continuous_auto_repeat():
    latch = KeyLatch()
    assert latch.press(32, 0)
    for now in (0.1, 0.2, 0.3, 0.4, 0.5):
        assert not latch.press(32, now)
    assert not latch.press(-1, 0.9)
    assert latch.press(32, 1)


@pytest.mark.parametrize("close", [False, True])
def test_opencv_waits_for_start_controls_pause_repeat_and_window_close(
    tmp_path, monkeypatch, close
):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(256)))
    shown = []
    names = []
    clock = [0.0]
    steps = iter(
        [
            (0, -1),
            (100, -1),
            (100.01, 32),
            (100.03, -1),
            (100.04, 32),
            (100.07, -1),
            (100.4, 32),
            (100.8, -1),
            (101, 32),
            (101.1, -1),
            (101.2, -1 if close else 27),
        ]
    )
    snapshots = []

    def wait(delay):
        now, key = next(steps)
        clock[0] = now
        snapshots.append((now, len(shown)))
        return key

    monkeypatch.setattr(opencv_player.sys, "platform", "linux")
    monkeypatch.setattr(opencv_player.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(cv2, "namedWindow", lambda name, flags: names.append(flags))
    monkeypatch.setattr(cv2, "imshow", lambda name, image: shown.append(image.copy()))
    monkeypatch.setattr(cv2, "waitKey", wait)
    monkeypatch.setattr(
        cv2, "getWindowProperty", lambda *args: 0 if close and clock[0] >= 101.2 else 1
    )
    monkeypatch.setattr(cv2, "destroyWindow", lambda *args: None)
    assert opencv_player.play_opencv(source) == 130
    assert names == [cv2.WINDOW_AUTOSIZE]
    assert snapshots[:3] == [(0, 1), (100, 1), (100.01, 1)]
    # At 100.04 the held/repeated Space does not toggle or redraw.
    assert snapshots[3][1] == snapshots[4][1] == snapshots[5][1]
    # Paused from 100.4 to 101, keeping both frame and region stable.
    assert snapshots[7][1] == snapshots[8][1]
    assert all(frame.shape == shown[0].shape for frame in shown)

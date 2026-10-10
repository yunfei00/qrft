"""Real Qt events, shared protocol, export and bounded playback lifecycle."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qrft.core.qr_decode import decode_qr_png
from qrft.encoder_gui.main import EncoderWindow
from qrft.encoder_gui.player import PlayerWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(app, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert condition()


def test_gui_metadata_and_png_export(app, tmp_path):
    source = tmp_path / "中文任意文件.exe"
    source.write_bytes(bytes(range(256)))
    window = EncoderWindow()
    try:
        window.source.setText(str(source))
        window.inspect_source()
        wait_until(app, lambda: not window.jobs)
        assert "中文任意文件.exe" in window.metadata.text()
        assert "SHA256" in window.metadata.text()
        window.output.setText(str(tmp_path / "png"))
        window.chunk_size.setValue(64)
        window.start_id.setValue(1)
        window.end_id.setValue(2)
        window.export_png()
        wait_until(app, lambda: not window.jobs)
        assert decode_qr_png(
            (tmp_path / "png" / "00000001-data.png").read_bytes()
        ).payload == bytes(range(64, 128))
        assert not (tmp_path / "png" / "00000000-data.png").exists()
    finally:
        window.close()


def test_real_player_pause_resume_stop_and_bounded_cache(app, tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(256)))
    seen = []
    window = PlayerWindow(
        source,
        chunk_size=32,
        interval_ms=10,
        initial_delay_ms=0,
        fullscreen=False,
        workers=1,
        prefetch=2,
    )
    window.progress.connect(lambda packet, count: seen.append(packet))
    try:
        window.toggle_pause()
        QTest.qWait(100)
        app.processEvents()
        assert not seen
        assert window.pending.qsize() <= 2
        window.toggle_pause()
        wait_until(app, lambda: window.finished)
        assert seen == ["START", *(f"{i:08d}" for i in range(8)), "FINISH"]
    finally:
        window.close()
    assert not window.thread.is_alive()


def test_close_during_initial_delay(app, tmp_path):
    source = tmp_path / "empty.bin"
    source.write_bytes(b"")
    window = PlayerWindow(source, initial_delay_ms=60000, fullscreen=False)
    window.close()
    assert not window.thread.is_alive()

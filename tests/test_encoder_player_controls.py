"""Real QR images; mock only OpenCV desktop keys and window I/O."""

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from qrft.encoder_cli import opencv_player
from qrft.encoder_cli.recording import FOOTER, HEADER, PADDING, QR_SIDE, KeyLatch, recording_canvas


def test_full_density_recording_window_fits_1080p_work_area():
    # A 40px taskbar and 40px window decoration allowance leave 1000px for content.
    assert HEADER + QR_SIDE + FOOTER + 40 <= 1080 - 40
    assert QR_SIDE + 2 * PADDING + 40 <= 1920


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

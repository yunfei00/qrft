"""Fixed-window player: first QR waits for Space; no automatic countdown."""

import sys
import time
from pathlib import Path

from qrft.encoder_cli.playback import iter_encoded_frames
from qrft.encoder_cli.prefetch import prefetch_png
from qrft.encoder_cli.recording import KeyLatch, recording_canvas


def play_opencv(
    source: Path,
    *,
    protocol_version=2,
    chunk_size=None,
    interval_ms=None,
    initial_delay_ms=0,
    retransmit=None,
    start_id=0,
    end_id=None,
    fullscreen=False,
    exit_when_finished=False,
):
    if protocol_version != 2:
        raise ValueError("OpenCV path currently requires v2; use the Qt player for v1")
    interval_ms = 50 if interval_ms is None else interval_ms
    if interval_ms < 1 or initial_delay_ms < 0:
        raise ValueError("invalid playback timing")
    import cv2
    import numpy as np

    user32 = None
    work_area = None
    if sys.platform == "win32":
        import ctypes

        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.SetProcessDPIAware()
        from ctypes.wintypes import RECT

        work_area = RECT()
        if not user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0):
            raise OSError("无法获取 Windows 可用显示区域")
    frames = prefetch_png(
        iter_encoded_frames(
            source,
            protocol_version=2,
            chunk_size=chunk_size,
            retransmit=retransmit,
            start_id=start_id,
            end_id=end_id,
        ),
        protocol_version=2,
        workers=2,
        capacity=4,
    )
    name = "QRFT v2 | Space: start/pause/resume | Esc: stop"
    opened = False
    started, paused, finished = False, True, False
    latch = KeyLatch()
    physical_space = False
    deadline = float("inf")

    def load(item):
        (label, _), png = item
        image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise OSError("cannot load QR image")
        return label, image

    def display(label, image):
        state = (
            "FINISHED"
            if finished
            else ("READY" if not started else ("PAUSED" if paused else "PLAYING"))
        )
        canvas = recording_canvas(image, label, state)
        if user32:
            width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            if not fullscreen:
                width = work_area.right - work_area.left
                height = work_area.bottom - work_area.top
            if canvas.shape[1] > width - (0 if fullscreen else 40) or canvas.shape[0] > height - (
                0 if fullscreen else 70
            ):
                raise ValueError("显示器空间不足；无法完整显示固定录屏区，请使用更大屏幕")
            if fullscreen:
                screen = np.full((height, width, 3), 245, np.uint8)
                y, x = (height - canvas.shape[0]) // 2, (width - canvas.shape[1]) // 2
                screen[y : y + canvas.shape[0], x : x + canvas.shape[1]] = canvas
                canvas = screen
        elif fullscreen:
            raise ValueError("OpenCV 全屏像素布局目前仅支持 Windows；默认窗口模式可用")
        cv2.imshow(name, canvas)

    try:
        label, image = load(next(frames))
        cv2.namedWindow(name, cv2.WINDOW_NORMAL if fullscreen else cv2.WINDOW_AUTOSIZE)
        opened = True
        if fullscreen:
            cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        elif user32:
            cv2.moveWindow(
                name,
                work_area.left + max(0, (work_area.right - work_area.left - 946) // 2),
                work_area.top,
            )
        display(label, image)
        while True:
            key = cv2.waitKey(5) & 0xFF
            now = time.monotonic()
            try:
                visible = cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) >= 1
            except cv2.error:
                visible = False
            if key == 27 or not visible:
                return 0 if finished else 130
            if user32:
                down = bool(user32.GetAsyncKeyState(0x20) & 0x8000)
                handle = user32.FindWindowW(None, name)
                pressed = down and not physical_space and user32.GetForegroundWindow() == handle
                physical_space = down
            else:
                pressed = latch.press(key, now)
            if pressed and not finished:
                started = True
                paused = not paused
                deadline = now + (50 if label in ("START", "FINISH") else interval_ms) / 1000
                display(label, image)
            if not started or paused or finished or now < deadline:
                continue
            try:
                label, image = load(next(frames))
            except StopIteration:
                finished = True
                display(label, image)
                if exit_when_finished:
                    return 0
                continue
            display(label, image)
            deadline = (
                time.monotonic() + (50 if label in ("START", "FINISH") else interval_ms) / 1000
            )
    finally:
        frames.close()
        if opened:
            try:
                cv2.destroyWindow(name)
            except cv2.error:
                pass  # User already closed this window; no other windows are destroyed.

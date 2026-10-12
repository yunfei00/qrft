"""Actual Windows OpenCV window and native Space/Esc smoke, not screen recording."""

import argparse
import ctypes
import json
import threading
import time
import uuid
from pathlib import Path

import cv2

from qrft.encoder_cli.opencv_player import play_opencv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--close-before-start", action="store_true")
    args = parser.parse_args()
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.PostMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    root = Path("temp") / ("p8-native-player-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    source = root / "native.bin"
    source.write_bytes(bytes(range(256)) * 6)
    shown = []
    original = cv2.imshow
    errors = []
    evidence = {"scope": "native OpenCV window/key smoke; no Snipping Tool recording"}
    title = "QRFT v2 | Space: start/pause/resume | Esc: stop"

    def display(name, image):
        shown.append(image.shape)
        original(name, image)

    def keyboard():
        handle = None
        try:
            deadline = time.monotonic() + 10
            while not shown and time.monotonic() < deadline:
                time.sleep(0.05)
            assert shown, "first QR was not displayed"
            handle = user32.FindWindowW(None, title)
            assert handle
            time.sleep(0.5)
            assert len(shown) == 1, "first QR did not remain stationary"
            evidence["stationary_first_frame"] = True
            if args.close_before_start:
                user32.PostMessageW(handle, 0x0010, 0, 0)
                evidence["native_window_close"] = True
                return

            def key(code, hold=0.08):
                user32.SetForegroundWindow(handle)
                time.sleep(0.1)
                if user32.GetForegroundWindow() != handle:
                    raise RuntimeError("Cannot focus own player; no keystrokes were injected")
                user32.keybd_event(code, 0, 0, 0)
                try:
                    time.sleep(hold)
                finally:
                    user32.keybd_event(code, 0, 2, 0)
                time.sleep(0.1)

            key(0x20, 0.8)
            assert len(shown) > 5, "held Space repeatedly toggled or did not start"
            key(0x20)
            count = len(shown)
            time.sleep(0.3)
            assert len(shown) == count, "Space did not pause"
            key(0x20)
            time.sleep(3)
            assert len(shown) > count, "Space did not resume"
            evidence["space_start_pause_resume_held_key"] = True
            key(0x1B)
        except (AssertionError, RuntimeError, OSError) as exc:
            errors.append(str(exc))
            if handle:
                user32.PostMessageW(handle, 0x0010, 0, 0)  # Close only our own test window.

    cv2.imshow = display
    thread = threading.Thread(target=keyboard, daemon=True)
    thread.start()
    try:
        code = play_opencv(source, fullscreen=args.fullscreen)
        thread.join(timeout=10)
        evidence.update(
            exit_code=code,
            errors=errors,
            fixed_shape=list(set(shown)),
            displayed_updates=len(shown),
        )
        (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        assert not errors and not thread.is_alive(), evidence
        assert code == (130 if args.close_before_start else 0) and len(set(shown)) == 1, evidence
        mode = (
            "window close before start"
            if args.close_before_start
            else "Space/Esc start/pause/resume"
        )
        print(f"PASS: native window, stationary first frame, {mode}; evidence: {root}")
    finally:
        cv2.imshow = original


if __name__ == "__main__":
    main()

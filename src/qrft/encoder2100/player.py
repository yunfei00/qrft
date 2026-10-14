"""Fixed-pixel OpenCV player with bounded asynchronous rendering and no frame loss."""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import nullcontext
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import lru_cache

from .protocol import FINISH_ID, START_ID

TITLE = "QRFT2100 | Space start/pause/resume | Esc exit"
WIDTH, HEIGHT = 945, 1010
QR_X, QR_Y, QR_SIZE = 10, 35, 925


@lru_cache(maxsize=2)
def render(text):
    from .qr import image

    return image(text)


def canvas(picture, label, state, position, total):
    import cv2
    import numpy as np

    pixels = np.asarray(picture)
    if pixels.shape != (QR_SIZE, QR_SIZE, 3):
        raise ValueError("二维码尺寸错误；禁止自动缩放")
    result = np.full((HEIGHT, WIDTH, 3), 235, dtype=np.uint8)
    result[QR_Y : QR_Y + QR_SIZE, QR_X : QR_X + QR_SIZE] = pixels[:, :, ::-1]
    cv2.putText(result, "RECORD COMPLETE WHITE QR REGION", (10, 23), 0, 0.55, (30, 30, 30), 1)
    text = f"{state} | ID {label:08d} | {position}/{total} | remaining {total - position}"
    cv2.putText(result, text, (10, 980), 0, 0.48, (30, 30, 30), 1)
    cv2.putText(
        result, "Space: start / pause / resume    Esc: exit", (10, 1002), 0, 0.5, (30, 30, 30), 1
    )
    return result


@dataclass
class State:
    interval: float
    status: str = "READY"
    deadline: float = float("inf")

    def space(self, now):
        if self.status == "FINISHED":
            return
        if self.status in ("READY", "PAUSED"):
            self.status = "PLAYING"
            self.deadline = now + self.interval
        else:
            self.status = "PAUSED"

    def due(self, now):
        return self.status in ("PLAYING", "BUFFERING") and now >= self.deadline


@dataclass
class KeyEdge:
    down: bool = False
    last: float = -1.0

    def press(self, key, now, *, down=None, focused=True):
        if down is None:
            edge = key == 32 and now - self.last > 0.3
            if key == 32:
                self.last = now
            return edge
        # waitKey preserves a short tap even when key-up precedes physical polling.
        # Typematic events while physically down never toggle a second time.
        edge = focused and (
            (down and not self.down)
            or (key == 32 and not down and not self.down and now - self.last > 0.25)
        )
        self.down = down
        if edge:
            self.last = now
        return edge


def resolve_workers(requested: int | None) -> int:
    """Use up to three local QR generators unless explicitly overridden."""
    if requested is None:
        return max(1, min(3, os.cpu_count() or 1))
    if not 1 <= requested <= 8:
        raise ValueError("workers 需为 1～8")
    return requested


class Frames:
    """At most capacity futures; hashing/reading stays in the parent process."""

    def __init__(self, frames, capacity, workers=None):
        self.frames = iter(frames)
        self.capacity = capacity
        self.queue = deque()
        self.pool = ProcessPoolExecutor(max_workers=resolve_workers(workers))
        self.exhausted = False

    def fill(self):
        while not self.exhausted and len(self.queue) < self.capacity:
            try:
                packet_id, text = next(self.frames)
            except StopIteration:
                self.exhausted = True
                break
            self.queue.append((packet_id, self.pool.submit(render, text)))

    def close(self):
        self.frames.close()
        for _, future in self.queue:
            future.cancel()
        self.pool.shutdown(wait=True, cancel_futures=True)


def windows_desktop(fullscreen):
    if sys.platform != "win32":
        if fullscreen:
            raise ValueError("全屏像素布局仅支持 Windows")
        return None, None
    import ctypes
    from ctypes.wintypes import RECT

    user = ctypes.windll.user32
    user.SetProcessDPIAware()
    user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user.FindWindowW.restype = ctypes.c_void_p
    user.GetForegroundWindow.restype = ctypes.c_void_p
    rect = RECT()
    if fullscreen:
        rect.right, rect.bottom = user.GetSystemMetrics(0), user.GetSystemMetrics(1)
    elif not user.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
        raise OSError("无法读取显示器可用区域")
    if rect.right - rect.left < WIDTH + (0 if fullscreen else 20) or rect.bottom - rect.top < (
        HEIGHT + (0 if fullscreen else 45)
    ):
        raise ValueError("屏幕空间不足，需完整显示 945×1010 客户区；不裁切或缩小二维码")
    return user, rect


def play(source, ranges, *, log_path=None, interval_ms=50, fullscreen=False, capacity=4, workers=None):
    import cv2

    if not 1 <= interval_ms <= 60000 or not 1 <= capacity <= 16:
        raise ValueError("interval-ms 需为 1～60000；prefetch 需为 1～16")
    effective_workers = resolve_workers(workers)
    frames = source.frames(ranges)
    label, text = next(frames)
    picture = render(text)  # START preflight before opening a window or writing logs.
    user, rect = windows_desktop(fullscreen)
    total = 40 + sum(b - a + 1 for a, b in ranges)
    state, position = State(interval_ms / 1000), 1
    latch = KeyEdge()
    opened = False
    pending = None
    selected_data = sum(b - a + 1 for a, b in ranges)
    shown_data = 0
    last_progress = 0.0
    # Default playback writes no files. Detailed JSONL is explicit opt-in only.
    log_context = (
        log_path.open("x", encoding="utf-8", buffering=1)
        if log_path is not None
        else nullcontext()
    )
    with log_context as log:

        def record(event, **fields):
            if log is not None:
                log.write(json.dumps({"event": event, "time": time.perf_counter(), **fields}) + "\n")

        def progress(*, force=False):
            nonlocal last_progress
            now = time.perf_counter()
            if not force and now - last_progress < 0.5 and shown_data < selected_data:
                return
            last_progress = now
            percent = 100.0 if not selected_data else shown_data / selected_data * 100
            line = (
                f"\rDATA {shown_data}/{selected_data} ({percent:.1f}%) "
                f"| 总帧 {position}/{total} | {state.status}"
            )
            print(line, end="\n" if force else "", flush=True)

        def display():
            pixels = canvas(picture, label, state.status, position, total)
            if fullscreen:
                import numpy as np

                screen = np.full((rect.bottom, rect.right, 3), 235, dtype=np.uint8)
                y, x = (rect.bottom - HEIGHT) // 2, (rect.right - WIDTH) // 2
                screen[y : y + HEIGHT, x : x + WIDTH] = pixels
                pixels = screen
            cv2.imshow(TITLE, pixels)

        try:
            cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL if fullscreen else cv2.WINDOW_AUTOSIZE)
            opened = True
            if fullscreen:
                cv2.setWindowProperty(TITLE, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            elif rect:
                cv2.moveWindow(TITLE, rect.left + (rect.right - rect.left - WIDTH) // 2, rect.top)
            display()
            record("display", packet_id=label, position=position, state=state.status)
            print(
                f"QRFT2100 已就绪：DATA {selected_data} 包，默认50ms，"
                f"生成进程 {effective_workers}，按 Space 开始/暂停，Esc 退出。",
                flush=True,
            )
            # Keep compatibility with 2-arg test doubles when auto worker selection is used.
            pending = Frames(frames, capacity) if workers is None else Frames(frames, capacity, workers)
            pending.fill()
            while True:
                key = cv2.waitKey(5) & 255
                now = time.perf_counter()
                try:
                    visible = cv2.getWindowProperty(TITLE, cv2.WND_PROP_VISIBLE) >= 1
                except cv2.error:
                    visible = False
                if key == 27 or not visible:
                    record("exit", complete=state.status == "FINISHED", position=position)
                    progress(force=True)
                    if state.status != "FINISHED":
                        print("播放提前结束；已显示进度如上。", flush=True)
                    return 0 if state.status == "FINISHED" else 130
                if user:
                    down = bool(user.GetAsyncKeyState(32) & 0x8000)
                    edge = latch.press(
                        key,
                        now,
                        down=down,
                        focused=user.GetForegroundWindow() == user.FindWindowW(None, TITLE),
                    )
                else:
                    edge = latch.press(key, now)
                if edge:
                    state.space(now)
                    display()
                    record("state", state=state.status, position=position)
                    progress(force=True)
                if not state.due(now):
                    continue
                if not pending.queue:
                    state.status = "FINISHED"
                    display()
                    record("completed", position=position)
                    progress(force=True)
                    print("播放完成；请先保存录屏，再按 Esc 关闭。", flush=True)
                    continue
                packet_id, future = pending.queue[0]
                if not future.done():
                    if state.status != "BUFFERING":
                        state.status = "BUFFERING"
                        display()
                        record("buffering", position=position)
                        print("二维码正在生成，保持上一帧等待；不会跳包。", flush=True)
                    continue
                picture = future.result()
                pending.queue.popleft()
                label, position = packet_id, position + 1
                state.status = "PLAYING"
                display()
                shown = time.perf_counter()
                record("display", packet_id=label, position=position, state=state.status)
                state.deadline = shown + state.interval
                if packet_id not in (START_ID, FINISH_ID):
                    shown_data += 1
                    progress()
                pending.fill()
        except cv2.error as exc:
            record("failed", error="OpenCV", position=position)
            raise RuntimeError("OpenCV 播放窗口失败；请检查本地图形桌面与播放日志") from exc
        except BaseException as exc:
            record("failed", error=type(exc).__name__, position=position)
            raise
        finally:
            if pending:
                pending.close()
            else:
                frames.close()
            if opened:
                try:
                    cv2.destroyWindow(TITLE)
                except cv2.error:
                    pass

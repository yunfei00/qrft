"""有界二维码预生成队列：后台线程生成 PNG，前台只消费已完成帧。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor

from qrft.core.qr_image import render_png


def ordered_prefetch[T](
    items: Iterable[T],
    transform: Callable[[T], bytes],
    *,
    workers: int = 2,
    capacity: int = 4,
) -> Iterator[tuple[T, bytes]]:
    """至多 capacity 个待处理任务，保序输出，迭代器关闭时释放线程。"""
    if workers < 1 or capacity < 1 or capacity < workers:
        raise ValueError("require 1 <= workers <= capacity")
    iterator = iter(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: list[tuple[T, Future[bytes]]] = []

        def fill() -> None:
            while len(pending) < capacity:
                try:
                    item = next(iterator)
                except StopIteration:
                    break
                pending.append((item, pool.submit(transform, item)))

        try:
            fill()
            while pending:
                item, future = pending.pop(0)
                yield item, future.result()
                fill()
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                close()


def prefetch_png(
    frames: Iterable[tuple[str, bytes]],
    *,
    workers: int = 2,
    capacity: int = 4,
    qr_options: dict | None = None,
    protocol_version: int = 2,
) -> Iterator[tuple[tuple[str, bytes], bytes]]:
    """对原始 QRFT 帧进行有界并行 PNG 生成。"""

    def render(frame: tuple[str, bytes]) -> bytes:
        return render_png(frame[1], protocol_version=protocol_version, **(qr_options or {}))

    return ordered_prefetch(frames, render, workers=workers, capacity=capacity)

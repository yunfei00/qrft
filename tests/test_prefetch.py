"""有界并行队列的保序、限流及异常验证。"""

from threading import Event

import pytest

from qrft.encoder_cli.prefetch import ordered_prefetch


def test_prefetch_keeps_original_order() -> None:
    result = list(
        ordered_prefetch(range(10), lambda value: str(value).encode(), workers=3, capacity=4)
    )
    assert result == [(value, str(value).encode()) for value in range(10)]


def test_prefetch_never_consumes_more_than_capacity_before_first_yield() -> None:
    release = Event()

    def transform(value: int) -> bytes:
        if value == 0:
            release.wait(timeout=2)
        return bytes([value])

    pulled: list[int] = []

    def source():
        for value in range(20):
            pulled.append(value)
            yield value

    iterator = ordered_prefetch(source(), transform, workers=2, capacity=3)
    try:
        assert next(iterator) == (0, b"\x00")
        assert len(pulled) == 3
    finally:
        release.set()
        iterator.close()


@pytest.mark.parametrize("workers,capacity", [(0, 1), (1, 0), (3, 2)])
def test_invalid_prefetch_config(workers: int, capacity: int) -> None:
    with pytest.raises(ValueError):
        list(ordered_prefetch([], bytes, workers=workers, capacity=capacity))

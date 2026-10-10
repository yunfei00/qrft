"""Windows 全屏二维码播放器：空格暂停、Esc 停止。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def play(
    source: Path,
    *,
    chunk_size: int = 256,
    interval_ms: int = 300,
    initial_delay_ms: int = 3000,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    fullscreen: bool = True,
    workers: int = 2,
    prefetch: int = 4,
) -> int:
    """延迟启动并按定时器显示二维码，数据帧在播放时才生成。"""
    if interval_ms < 1 or initial_delay_ms < 0:
        raise ValueError("invalid interval or initial delay")
    if workers < 1 or prefetch < workers:
        raise ValueError("require 1 <= workers <= prefetch")

    from PySide6.QtWidgets import QApplication

    from qrft.encoder_gui.player import PlayerWindow

    existing_app = QApplication.instance()
    app = existing_app or QApplication(sys.argv)
    window = PlayerWindow(
        source,
        chunk_size=chunk_size,
        interval_ms=interval_ms,
        initial_delay_ms=initial_delay_ms,
        retransmit=retransmit,
        start_id=start_id,
        end_id=end_id,
        fullscreen=fullscreen,
        workers=workers,
        prefetch=prefetch,
    )
    window.show()
    if existing_app is not None:
        windows = app.property("qrft_players") or []
        windows.append(window)
        app.setProperty("qrft_players", windows)
        window.stopped.connect(lambda: windows.remove(window) if window in windows else None)
        return 0
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRFT 全屏实时二维码播放器")
    parser.add_argument("source", type=Path)
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--interval-ms", type=int, default=300)
    parser.add_argument("--initial-delay-ms", type=int, default=3000)
    parser.add_argument("--retransmit", type=Path)
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--end-id", type=int)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--prefetch", type=int, default=4)
    parser.add_argument("--windowed", action="store_true")
    args = parser.parse_args(argv)
    return play(
        args.source,
        chunk_size=args.chunk_size,
        interval_ms=args.interval_ms,
        initial_delay_ms=args.initial_delay_ms,
        retransmit=args.retransmit,
        start_id=args.start_id,
        end_id=args.end_id,
        fullscreen=not args.windowed,
        workers=args.workers,
        prefetch=args.prefetch,
    )


if __name__ == "__main__":
    raise SystemExit(main())

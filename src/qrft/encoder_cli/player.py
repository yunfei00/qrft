"""Windows 全屏二维码播放器：空格暂停、Esc 停止。"""

from __future__ import annotations

import sys
from pathlib import Path


def play(
    source: Path,
    *,
    chunk_size: int | None = None,
    interval_ms: int | None = None,
    initial_delay_ms: int = 3000,
    retransmit: Path | None = None,
    start_id: int = 0,
    end_id: int | None = None,
    fullscreen: bool = False,
    workers: int = 2,
    prefetch: int = 4,
    exit_when_finished: bool = False,
    protocol_version: int = 1,
) -> int:
    """延迟启动并按定时器显示二维码，数据帧在播放时才生成。"""
    interval_ms = interval_ms if interval_ms is not None else (50 if protocol_version == 2 else 300)
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
        protocol_version=protocol_version,
        chunk_size=chunk_size,
        interval_ms=interval_ms,
        initial_delay_ms=initial_delay_ms,
        retransmit=retransmit,
        start_id=start_id,
        end_id=end_id,
        fullscreen=fullscreen,
        workers=workers,
        prefetch=prefetch,
        exit_when_finished=exit_when_finished,
    )
    window.show()
    if existing_app is not None:
        windows = app.property("qrft_players") or []
        windows.append(window)
        app.setProperty("qrft_players", windows)
        window.stopped.connect(lambda: windows.remove(window) if window in windows else None)
        return 0
    code = app.exec()
    return 1 if window.error else code


def main(argv: list[str] | None = None) -> int:
    import sys

    from qrft.encoder_cli.entrypoint import main as console_main

    return console_main(["play", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())

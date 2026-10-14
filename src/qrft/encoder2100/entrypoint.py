"""Frozen console entry; dispatch Windows multiprocessing before the CLI gate."""

from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from qrft.encoder2100.cli import main

    raise SystemExit(main())

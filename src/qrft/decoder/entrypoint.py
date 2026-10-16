"""Open the decoder desktop, with an explicit distributed worker command."""

import sys

from qrft.decoder.worker import main as worker_main


def gui_main(argv: list[str]) -> int:
    from qrft.decoder_gui.main import main as desktop_main

    return desktop_main(argv)


def control_main(argv: list[str]) -> int:
    from qrft.control.app import main as server_main

    server_main(argv)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "worker":
        return worker_main(args[1:])
    if args and args[0] == "control":
        return control_main(args[1:])
    return gui_main(args)


if __name__ == "__main__":
    raise SystemExit(main())

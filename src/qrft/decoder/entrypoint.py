"""Preserve local recovery commands and expose the distributed worker in the EXE."""

import sys

from qrft.decoder.main import main as local_main
from qrft.decoder.worker import main as worker_main


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "worker":
        return worker_main(args[1:])
    return local_main(args)


if __name__ == "__main__":
    raise SystemExit(main())

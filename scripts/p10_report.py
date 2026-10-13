"""Export saved P10 measurements to small anonymized Markdown/JSON reports."""

import argparse
from pathlib import Path

from qrft.acceptance.p10_report import export

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs"))
    args = parser.parse_args()
    print(export(args.root, args.output)["core_gate"])

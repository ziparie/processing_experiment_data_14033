"""Command-line entry point.

Usage:
    python -m experiment_transform RAW_EXPORT.xlsx [-o OUTPUT.xlsx]
"""

import argparse
import sys
from pathlib import Path

from experiment_transform.transform import (
    InputLayoutError,
    load_export,
    transform,
    write_excel,
)

DEFAULT_SUFFIX = "_resolution_calibration.xlsx"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Qualtrics export into one row per respondent per "
            "question (Timing, Score, Confidence, Familiar)."
        )
    )
    parser.add_argument("input", type=Path, help="Raw Qualtrics .xlsx export")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"Output .xlsx (default: <input>{DEFAULT_SUFFIX})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the transformation and print a short report."""
    args = parse_args(argv)
    output = args.output or args.input.with_name(
        args.input.stem + DEFAULT_SUFFIX
    )

    try:
        result = transform(load_export(args.input))
    except InputLayoutError as error:
        print(
            f"Input file has an unexpected layout:\n{error}", file=sys.stderr
        )
        return 1

    write_excel(result, output)
    print(f"Respondents read:     {result.respondents_read}")
    print(
        f"Skipped (no consent): {len(result.respondents_skipped_no_consent)}"
    )
    print(f"Respondents written:  {result.respondents_written}")
    print(f"Rows written:         {len(result.data)}")
    print(f"Issues reported:      {len(result.issues)}")
    print(f"Output:               {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

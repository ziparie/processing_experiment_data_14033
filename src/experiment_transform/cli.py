"""Command-line entry point.

Usage:
    python -m experiment_transform RAW_EXPORT.xlsx [-o OUTPUT.xlsx]
"""

import argparse
import sys
from pathlib import Path

from experiment_transform.likert import LikertResult, calculate_likert
from experiment_transform.likert_output import append_likert_sheets
from experiment_transform.transform import (
    InputLayoutError,
    TransformResult,
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


def print_report(result: TransformResult, output: Path) -> None:
    """Print the end-of-run counts with aligned labels."""
    lines = [
        ("Respondents read:", result.respondents_read),
        ("Excluded (preview):", result.excluded_preview),
        ("Excluded (other channel):", result.excluded_other_channel),
        ("Skipped (no consent):", len(result.respondents_skipped_no_consent)),
        (
            "Processed without consent:",
            len(result.respondents_without_consent),
        ),
        ("Respondents written:", result.respondents_written),
        ("Answered all questions:", len(result.answered_all_ids)),
        ("Students (of respondents written):", len(result.student_ids)),
        ("Students (of answered all):", result.students_answered_all),
        ("Student question unanswered:", len(result.student_unanswered_ids)),
        ("Rows written:", len(result.data)),
        ("Issues reported:", len(result.issues)),
        ("Output:", output),
    ]
    width = max(len(label) for label, _ in lines)
    for label, value in lines:
        print(f"{label:<{width}} {value}")


def print_likert_report(likert: LikertResult) -> None:
    """Print a short summary of the Likert sheets."""
    lines = [
        ("Likert participants:", likert.participants),
        ("Likert complete:", likert.complete),
        ("Likert partial:", likert.partial),
    ]
    width = max(len(label) for label, _ in lines)
    for label, value in lines:
        print(f"{label:<{width}} {value}")


def main(argv: list[str] | None = None) -> int:
    """Run the transformation and print a short report."""
    args = parse_args(argv)
    output = args.output or args.input.with_name(
        args.input.stem + DEFAULT_SUFFIX
    )

    try:
        raw = load_export(args.input)
        result = transform(raw)
        likert = calculate_likert(raw)
    except InputLayoutError as error:
        print(
            f"Input file has an unexpected layout:\n{error}", file=sys.stderr
        )
        return 1

    if result.respondents_written == 0:
        print(
            "No respondents to write; no output file was created.\n"
            f"Rows read: {result.respondents_read} "
            f"(anonymous: {result.respondents_anonymous}, "
            f"preview: {result.excluded_preview}, "
            f"other channel: {result.excluded_other_channel}).\n"
            "Skipped (no consent): "
            f"{len(result.respondents_skipped_no_consent)}.",
            file=sys.stderr,
        )
        return 1

    result.issues.extend(likert.issues)
    write_excel(result, output)
    append_likert_sheets(likert, output)
    print_report(result, output)
    print_likert_report(likert)
    return 0


if __name__ == "__main__":
    sys.exit(main())

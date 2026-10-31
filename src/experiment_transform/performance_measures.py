"""Compare each person's time, confidence and score across question groups.

Only questions with both a score and a confidence are used, as in the
calibration sheets, so a person's Unknown averages match the unknown
calibration sheet. Each person also gets a count of the questions left out
because they have only one of the two values.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

import pandas as pd

from experiment_transform import config

CORRECT_SHEET: Final[str] = "Correct vs Incorrect"
KNOWN_SHEET: Final[str] = "Known vs Unknown"

CORRECT_GROUPS: Final[dict[str, int]] = {
    "Correct": config.CORRECT_SCORE,
    "Incorrect": config.INCORRECT_SCORE,
}
KNOWN_GROUPS: Final[dict[str, int]] = {
    "Known": config.KNOWN,
    "Unknown": config.UNKNOWN,
}

# Name used in the sheet -> column in the Data table.
CORRECT_MEASURES: Final[dict[str, str]] = {
    "Time": "Timing",
    "Confidence": "Confidence",
}
KNOWN_MEASURES: Final[dict[str, str]] = {
    **CORRECT_MEASURES,
    "Score": "Score",
}


def _group_stats(
    label: str, rows: pd.DataFrame, measures: Mapping[str, str]
) -> dict[str, object]:
    """Return N and the average and sample stdev of each measure."""
    stats: dict[str, object] = {f"{label} N": len(rows)}
    for name, column in measures.items():
        stats[f"{label} Avg {name}"] = rows[column].mean()
        stats[f"{label} Stdev {name}"] = rows[column].std()
    return stats


def _person_row(
    user_id: str,
    rows: pd.DataFrame,
    group_column: str,
    groups: Mapping[str, int],
    measures: Mapping[str, str],
) -> dict[str, object]:
    has_score = rows["Score"].notna()
    has_confidence = rows["Confidence"].notna()
    paired = rows[has_score & has_confidence]
    row: dict[str, object] = {
        "UserId": user_id,
        "Only Score": (has_score & ~has_confidence).sum(),
        "Only Confidence": (has_confidence & ~has_score).sum(),
    }
    for label, value in groups.items():
        group_rows = paired[paired[group_column] == value]
        row.update(_group_stats(label, group_rows, measures))
    return row


def _compare(
    data: pd.DataFrame,
    group_column: str,
    groups: Mapping[str, int],
    measures: Mapping[str, str],
) -> pd.DataFrame:
    """Return one row per UserId, in the order people appear in the data."""
    return pd.DataFrame(
        [
            _person_row(user_id, rows, group_column, groups, measures)
            for user_id, rows in data.groupby("UserId", sort=False)
        ]
    )


def calculate_correct(data: pd.DataFrame) -> pd.DataFrame:
    """Compare questions answered correctly and incorrectly."""
    return _compare(data, "Score", CORRECT_GROUPS, CORRECT_MEASURES)


def calculate_known(data: pd.DataFrame) -> pd.DataFrame:
    """Compare questions the person knew and did not know."""
    return _compare(data, "Familiar", KNOWN_GROUPS, KNOWN_MEASURES)


def append_sheets(data: pd.DataFrame, path: Path) -> None:
    """Add both comparison sheets to a workbook that already exists."""
    sheets = {
        CORRECT_SHEET: calculate_correct(data),
        KNOWN_SHEET: calculate_known(data),
    }
    with pd.ExcelWriter(path, engine="openpyxl", mode="a") as writer:
        for name, table in sheets.items():
            table.to_excel(writer, sheet_name=name, index=False)

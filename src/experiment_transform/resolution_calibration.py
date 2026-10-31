"""Calculate calibration and resolution for each person from the Data table.

Only questions with both a score and a confidence are used, so a person's two
averages cover the same questions and the gamma matches SPSS, which drops a
case that is missing either variable:

    CROSSTABS
      /TABLES=success BY JOL BY student
      /FORMAT=AVALUE TABLES
      /STATISTICS=GAMMA
      /CELLS=COUNT
      /COUNT ROUND CELL.

Here success is Score, JOL is Confidence and student is UserId.

The same values are also calculated over only the questions a person did not
know, for a separate sheet.
"""

import math
from collections.abc import Sequence
from itertools import combinations
from pathlib import Path
from typing import Final

import pandas as pd

from experiment_transform import config

SHEET: Final[str] = "Resolution Calibration"
UNKNOWN_SHEET: Final[str] = "calibration-resolution-unknown"
UNKNOWN_COUNT: Final[str] = "Unknown Answers Used"
COLUMNS: Final[tuple[str, ...]] = (
    "UserId",
    "Questions Used",
    "Average Score",
    "Average Confidence",
    "Calibration",
    "Calibration Direction",
    "Concordant Pairs",
    "Discordant Pairs",
    "Gamma",
    "Gamma Note",
)

OVERCONFIDENCE: Final[str] = "Overconfidence"
UNDERCONFIDENCE: Final[str] = "Underconfidence"
NO_DIFFERENCE: Final[str] = "None"

NO_QUESTIONS_NOTE: Final[str] = "No question has both a score and a confidence"
NO_UNKNOWN_NOTE: Final[str] = (
    "No unknown question has both a score and a confidence"
)
EQUAL_SCORES_NOTE: Final[str] = "All scores are equal"
EQUAL_CONFIDENCE_NOTE: Final[str] = "All confidence ratings are equal"


def _sign(number: float) -> int:
    return (number > 0) - (number < 0)


def count_pairs(
    scores: Sequence[float], confidences: Sequence[float]
) -> tuple[int, int]:
    """Return concordant and discordant question pairs; ties are dropped."""
    concordant = 0
    discordant = 0
    pairs = zip(scores, confidences)
    for (score_a, conf_a), (score_b, conf_b) in combinations(pairs, 2):
        direction = _sign(score_a - score_b) * _sign(conf_a - conf_b)
        if direction > 0:
            concordant += 1
        elif direction < 0:
            discordant += 1
    return concordant, discordant


def goodman_kruskal_gamma(concordant: int, discordant: int) -> float | None:
    """Return (C - D) / (C + D), or None when every pair is tied."""
    total = concordant + discordant
    return None if total == 0 else (concordant - discordant) / total


def calibration_direction(
    average_score: float, average_confidence: float
) -> str:
    """Name the direction of the gap between confidence and score."""
    if math.isclose(
        average_confidence, average_score, abs_tol=config.ANSWER_TOLERANCE
    ):
        return NO_DIFFERENCE
    if average_confidence > average_score:
        return OVERCONFIDENCE
    return UNDERCONFIDENCE


def _gamma_note(scores: pd.Series, confidences: pd.Series) -> str | None:
    """Explain why gamma is empty."""
    notes = []
    if scores.nunique() < 2:
        notes.append(EQUAL_SCORES_NOTE)
    if confidences.nunique() < 2:
        notes.append(EQUAL_CONFIDENCE_NOTE)
    return "; ".join(notes) or None


def _person_row(
    user_id: str, rows: pd.DataFrame, no_questions_note: str
) -> dict[str, object]:
    paired = rows.dropna(subset=["Score", "Confidence"])
    if paired.empty:
        return {
            "UserId": user_id,
            "Questions Used": 0,
            "Gamma Note": no_questions_note,
        }

    scores = paired["Score"]
    confidences = paired["Confidence"]
    average_score = scores.mean()
    average_confidence = confidences.mean()
    concordant, discordant = count_pairs(
        scores.tolist(), confidences.tolist()
    )
    gamma = goodman_kruskal_gamma(concordant, discordant)
    return {
        "UserId": user_id,
        "Questions Used": len(paired),
        "Average Score": average_score,
        "Average Confidence": average_confidence,
        "Calibration": abs(average_score - average_confidence),
        "Calibration Direction": calibration_direction(
            average_score, average_confidence
        ),
        "Concordant Pairs": concordant,
        "Discordant Pairs": discordant,
        "Gamma": gamma,
        "Gamma Note": (
            _gamma_note(scores, confidences) if gamma is None else None
        ),
    }


def calculate(data: pd.DataFrame) -> pd.DataFrame:
    """Return one row per UserId, in the order people appear in the data."""
    rows = [
        _person_row(user_id, person_rows, NO_QUESTIONS_NOTE)
        for user_id, person_rows in data.groupby("UserId", sort=False)
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


def calculate_unknown(data: pd.DataFrame) -> pd.DataFrame:
    """Return one row per UserId, using only the questions they did not know.

    A person with no such questions keeps a row with a count of 0.
    """
    rows = [
        _person_row(
            user_id,
            person_rows[person_rows["Familiar"] == config.UNKNOWN],
            NO_UNKNOWN_NOTE,
        )
        for user_id, person_rows in data.groupby("UserId", sort=False)
    ]
    table = pd.DataFrame(rows, columns=COLUMNS)
    return table.rename(columns={"Questions Used": UNKNOWN_COUNT})


def append_sheet(table: pd.DataFrame, path: Path, sheet: str = SHEET) -> None:
    """Add a per-person sheet to a workbook that already exists."""
    with pd.ExcelWriter(path, engine="openpyxl", mode="a") as writer:
        table.to_excel(writer, sheet_name=sheet, index=False)

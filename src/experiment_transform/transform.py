"""Turn the Qualtrics export into one row per respondent per question."""

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from experiment_transform import config
from experiment_transform.questions import QUESTIONS, Question


class InputLayoutError(ValueError):
    """Raised when the export does not have the expected columns."""


@dataclass(frozen=True)
class Issue:
    """A value that could not be coded or looks suspicious."""

    user_id: str
    question: int | None
    variable: str
    raw_value: object
    message: str


@dataclass
class TransformResult:
    """Output table plus everything needed to audit it."""

    data: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)
    respondents_read: int = 0
    respondents_skipped_no_consent: list[str] = field(default_factory=list)

    @property
    def respondents_written(self) -> int:
        """Number of respondents that appear in the output."""
        return self.data["UserId"].nunique()


# --- Loading and layout checks -------------------------------------------


def load_export(path: Path) -> pd.DataFrame:
    """Read the export, keeping row 1 as header and dropping row 2.

    All cells are read as text so that coding decisions (e.g. "-99" stored
    as text) are made explicitly in this module, not by pandas.
    """
    return pd.read_excel(
        path,
        header=0,
        skiprows=[config.QUESTION_TEXT_ROW],
        dtype=str,
    )


def check_layout(raw: pd.DataFrame) -> None:
    """Verify that all expected columns exist and each block is contiguous.

    Raises:
        InputLayoutError: With a list of every problem found.
    """
    columns = list(raw.columns)
    problems = []
    for name in (config.ID_COLUMN, config.CONSENT_COLUMN):
        if name not in columns:
            problems.append(f"Missing column '{name}'.")

    for question in QUESTIONS:
        block = question.block_columns
        missing = [c for c in block if c not in columns]
        if missing:
            problems.append(
                f"Question {question.number}: missing columns {missing}."
            )
            continue
        start = columns.index(block[0])
        if tuple(columns[start : start + len(block)]) != block:
            problems.append(
                f"Question {question.number}: columns are not consecutive "
                f"in the expected order {list(block)}."
            )

    if problems:
        raise InputLayoutError("\n".join(problems))


# --- Value parsing ---------------------------------------------------------


def _is_empty(value: object) -> bool:
    return (
        value is None
        or (isinstance(value, float) and math.isnan(value))
        or (isinstance(value, str) and value.strip() == "")
    )


def parse_number(value: object) -> float | None:
    """Convert a cell to float; return None for empty or non-numeric text."""
    if _is_empty(value):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _is_unanswered(number: float | None) -> bool:
    return number is not None and number == config.UNANSWERED_CODE


# --- Coding of the four output variables -----------------------------------


def code_timing(raw_value: object) -> float | None:
    """Return timing in seconds, or None when not recorded."""
    number = parse_number(raw_value)
    return None if _is_unanswered(number) else number


def code_score(raw_value: object, correct_answer: float) -> float | None:
    """Return 100 if correct, 0 if wrong, None if unanswered."""
    number = parse_number(raw_value)
    if number is None or _is_unanswered(number):
        return None
    if math.isclose(number, correct_answer, abs_tol=config.ANSWER_TOLERANCE):
        return config.CORRECT_SCORE
    return config.INCORRECT_SCORE


def code_confidence(raw_value: object) -> float | None:
    """Return confidence as is, or None if unanswered."""
    number = parse_number(raw_value)
    return None if _is_unanswered(number) else number


def code_familiar(raw_value: object) -> int | None:
    """Apply FAMILIAR_CODING; None for an unknown code."""
    if _is_empty(raw_value):
        return config.FAMILIAR_IF_EMPTY
    number = parse_number(raw_value)
    if number is None or not number.is_integer():
        return None
    return config.FAMILIAR_CODING.get(int(number))


# --- Row building ----------------------------------------------------------


def _code_question(
    user_id: str, row: pd.Series, question: Question, issues: list[Issue]
) -> dict[str, object]:
    """Build one output row and record any value that needs attention."""
    timing_raw = row[question.timing_column(config.TIMING_MEASURE)]
    answer_raw = row[question.answer_column]
    confidence_raw = row[question.confidence_column]
    familiar_raw = row[question.familiar_column]

    def report(variable: str, raw: object, message: str) -> None:
        issues.append(Issue(user_id, question.number, variable, raw, message))

    if not _is_empty(timing_raw) and parse_number(timing_raw) is None:
        report("Timing", timing_raw, "Timing is not a number; left empty.")

    if not _is_empty(answer_raw) and parse_number(answer_raw) is None:
        report("Score", answer_raw, "Answer is not a number; left empty.")

    confidence = code_confidence(confidence_raw)
    if not _is_empty(confidence_raw) and parse_number(confidence_raw) is None:
        report(
            "Confidence",
            confidence_raw,
            "Confidence is not a number; left empty.",
        )
    elif confidence is not None and not (
        config.CONFIDENCE_MIN <= confidence <= config.CONFIDENCE_MAX
    ):
        report(
            "Confidence",
            confidence_raw,
            "Confidence outside 0-100; copied as is.",
        )

    familiar = code_familiar(familiar_raw)
    if familiar is None:
        report(
            "Familiar",
            familiar_raw,
            "Unexpected familiarity code; left empty.",
        )

    return {
        "UserId": user_id,
        "Question": question.number,
        "Timing": code_timing(timing_raw),
        "Score": code_score(answer_raw, question.correct_answer),
        "Confidence": confidence,
        "Familiar": familiar,
    }


def transform(raw: pd.DataFrame) -> TransformResult:
    """Convert the wide export into the long resolution/calibration table."""
    check_layout(raw)
    result = TransformResult(
        data=pd.DataFrame(columns=config.OUTPUT_COLUMNS),
        respondents_read=len(raw),
    )

    seen_ids: set[str] = set()
    rows: list[dict[str, object]] = []
    for _, row in raw.iterrows():
        user_id = row[config.ID_COLUMN]
        if _is_empty(user_id):
            result.issues.append(
                Issue(
                    "",
                    None,
                    "UserId",
                    user_id,
                    "Row without a ResponseId; skipped.",
                )
            )
            continue
        user_id = str(user_id).strip()

        if parse_number(row[config.CONSENT_COLUMN]) == config.NO_CONSENT_CODE:
            result.respondents_skipped_no_consent.append(user_id)
            continue

        if user_id in seen_ids:
            result.issues.append(
                Issue(
                    user_id,
                    None,
                    "UserId",
                    user_id,
                    "Duplicate ResponseId; both rows kept.",
                )
            )
        seen_ids.add(user_id)

        for question in QUESTIONS:
            rows.append(_code_question(user_id, row, question, result.issues))

    data = pd.DataFrame(rows, columns=config.OUTPUT_COLUMNS)
    for name in ("Timing", "Score", "Confidence", "Familiar"):
        data[name] = pd.to_numeric(data[name])
    data["Question"] = data["Question"].astype(int)
    result.data = data
    return result


# --- Output ------------------------------------------------------------------


def _summary_table(result: TransformResult) -> pd.DataFrame:
    skipped = result.respondents_skipped_no_consent
    lines = [
        ("Respondents in input", result.respondents_read),
        ("Skipped: no consent (Q1 = 2)", len(skipped)),
        ("Skipped IDs", ", ".join(skipped)),
        ("Respondents in output", result.respondents_written),
        ("Rows in output", len(result.data)),
        ("Issues reported", len(result.issues)),
        ("Timing measure used", config.TIMING_MEASURE),
        ("Missing values", "Empty cell (unanswered = -99 in raw data)"),
        (
            "Correct answers",
            ", ".join(f"Q{q.number}={q.correct_answer:g}" for q in QUESTIONS),
        ),
    ]
    return pd.DataFrame(lines, columns=["Item", "Value"])


def write_excel(result: TransformResult, path: Path) -> None:
    """Write data, summary and validation sheets to one workbook."""
    issues = pd.DataFrame(
        [vars(i) for i in result.issues],
        columns=["user_id", "question", "variable", "raw_value", "message"],
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        result.data.to_excel(writer, sheet_name=config.DATA_SHEET, index=False)
        _summary_table(result).to_excel(
            writer, sheet_name=config.SUMMARY_SHEET, index=False
        )
        issues.to_excel(
            writer, sheet_name=config.VALIDATION_SHEET, index=False
        )

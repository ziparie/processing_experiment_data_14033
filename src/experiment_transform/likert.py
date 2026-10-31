"""Settings and calculations for the Likert thinking-style index.

Participants are the respondents written to the Data sheet: the channel
filter and the consent rule of ``transform`` decide who is included, whatever
their Likert answers are.
"""

import math
import statistics
from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from experiment_transform import config
from experiment_transform.transform import (
    InputLayoutError,
    Issue,
    TransformResult,
    _excluded_by_channel,
    _has_any_answer,
    _is_empty,
    _is_unanswered,
    check_layout,
    parse_number,
)

# --- Items ---------------------------------------------------------------
# Bare column names, in export order. The "Q47_First Click" style columns
# are unrelated timing columns.
LIKERT_COLUMNS: Final[tuple[str, ...]] = (
    "Q47",
    "Q52",
    "Q51",
    "Q50",
    "Q49",
    "Q48",
)
REVERSED_COLUMNS: Final[frozenset[str]] = frozenset({"Q50", "Q51"})
SCALE_MIN: Final[int] = 1
SCALE_MAX: Final[int] = 5
REVERSE_FROM: Final[int] = SCALE_MIN + SCALE_MAX  # score = 6 - answer


# --- Groups --------------------------------------------------------------
@dataclass(frozen=True)
class GroupVariable:
    """A demographic column that participants are grouped by.

    Attributes:
        column: Column in the export.
        sheet: Name of the output sheet.
        label: Prefix for the name of a row with an unexpected code.
        groups: Answer code -> group name, in the order they are listed.
    """

    column: str
    sheet: str
    label: str
    groups: dict[int, str]


GROUP_VARIABLES: Final[tuple[GroupVariable, ...]] = (
    GroupVariable(
        config.GENDER_COLUMN,
        "Likert by Gender",
        "Gender",
        config.GENDER_GROUPS,
    ),
    GroupVariable(
        config.STUDENT_COLUMN,
        "Likert by Student",
        "Student",
        {config.STUDENT_CODE: "Yes", config.NOT_STUDENT_CODE: "No"},
    ),
    GroupVariable(
        config.AGE_COLUMN,
        "Likert by Age",
        "Age",
        config.AGE_GROUPS,
    ),
    GroupVariable(
        config.DEGREE_COLUMN,
        "Likert by Degree",
        "Degree",
        config.DEGREE_GROUPS,
    ),
)
UNANSWERED_GROUP: Final[str] = "Unanswered"

# --- Output --------------------------------------------------------------
SCORES_SHEET: Final[str] = "Likert Scores"
ITEMS_SHEET: Final[str] = "Likert Items"
SCORES_COLUMNS: Final[tuple[str, ...]] = (
    "UserId",
    "Cumulative",
    "Average",
    "Stdev",
)
ITEMS_COLUMNS: Final[tuple[str, ...]] = (
    "Question",
    "Reversed",
    "N",
    "Average",
    "Stdev",
    "Median",
)
GROUP_COLUMNS: Final[tuple[str, ...]] = (
    "Group",
    "N",
    "Cumulative Average",
    "Cumulative Stdev",
    "Average Average",
    "Average Stdev",
)


@dataclass
class LikertResult:
    """The content of the Likert sheets plus the issues found.

    Attributes:
        scores: One row per participant.
        items: One row per Likert item.
        groups: Output sheet name -> table with one row per group.
        issues: Entries for the Validation sheet.
        participants: Number of rows in ``scores``.
        complete: Participants with all six items valid.
        partial: Participants with some, but not all, items valid.
    """

    scores: pd.DataFrame
    items: pd.DataFrame
    groups: dict[str, pd.DataFrame] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    participants: int = 0
    complete: int = 0
    partial: int = 0


# --- Layout and selection ------------------------------------------------


def check_likert_layout(raw: pd.DataFrame) -> None:
    """Verify that every Likert and group column exists.

    Raises:
        InputLayoutError: With a list of every problem found.
    """
    needed = (*LIKERT_COLUMNS, *(g.column for g in GROUP_VARIABLES))
    problems = [
        f"Missing column '{name}'." for name in needed if name not in raw
    ]
    if problems:
        raise InputLayoutError("\n".join(problems))


def select_participants(raw: pd.DataFrame) -> list[pd.Series]:
    """Return the rows that ``transform`` writes to the Data sheet.

    Applies the same rules in the same order. Duplicate IDs are kept, as in
    Data, and were already reported there. Issues found on the way are
    discarded because ``transform`` reports them too.
    """
    scratch = TransformResult(data=pd.DataFrame())
    selected = []
    for _, row in raw.iterrows():
        if _excluded_by_channel(row, scratch):
            continue
        if _is_empty(row[config.ID_COLUMN]):
            continue
        consented = (
            parse_number(row[config.CONSENT_COLUMN]) == config.CONSENT_CODE
        )
        if consented or _has_any_answer(row):
            selected.append(row)
    return selected


# --- Scoring -------------------------------------------------------------


def parse_answer(raw_value: object) -> int | None:
    """Return the answer if it is an integer on the scale, otherwise None."""
    number = parse_number(raw_value)
    if number is None or not number.is_integer():
        return None
    answer = int(number)
    return answer if SCALE_MIN <= answer <= SCALE_MAX else None


def score_item(column: str, answer: int) -> int:
    """Return the score of an answer, reversing the reversed items."""
    return REVERSE_FROM - answer if column in REVERSED_COLUMNS else answer


def sample_stdev(values: list[float]) -> float | None:
    """Return the sample stdev (n-1), or None for fewer than two values."""
    return statistics.stdev(values) if len(values) >= 2 else None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _score_row(row: pd.Series, issues: list[Issue]) -> dict[str, int]:
    """Return the valid scores of a participant, by column."""
    user_id = str(row[config.ID_COLUMN]).strip()
    scores = {}
    for column in LIKERT_COLUMNS:
        raw_value = row[column]
        answer = parse_answer(raw_value)
        if answer is not None:
            scores[column] = score_item(column, answer)
        elif not _is_empty(raw_value) and not _is_unanswered(
            parse_number(raw_value)
        ):
            issues.append(
                Issue(
                    user_id,
                    None,
                    column,
                    raw_value,
                    f"Likert answer is not an integer {SCALE_MIN}-"
                    f"{SCALE_MAX}; treated as missing.",
                )
            )
    if 0 < len(scores) < len(LIKERT_COLUMNS):
        missing = [c for c in LIKERT_COLUMNS if c not in scores]
        issues.append(
            Issue(
                user_id,
                None,
                "Likert",
                f"{len(scores)} of {len(LIKERT_COLUMNS)}",
                f"Partial Likert answers, missing {', '.join(missing)}; "
                "no index score, left out of the group statistics.",
            )
        )
    return scores


def _participant_totals(
    scores: dict[str, int],
) -> tuple[float, float, float] | None:
    """Return cumulative, average and stdev, or None unless complete."""
    if len(scores) < len(LIKERT_COLUMNS):
        return None
    values = list(scores.values())
    return sum(values), statistics.fmean(values), statistics.stdev(values)


# --- Tables --------------------------------------------------------------


def _numeric_table(
    rows: list[tuple], columns: tuple[str, ...], numeric: tuple[str, ...]
) -> pd.DataFrame:
    """Build a table in which empty statistics are NaN, not None."""
    table = pd.DataFrame(rows, columns=columns)
    for name in numeric:
        table[name] = pd.to_numeric(table[name])
    return table


def _items_table(all_scores: list[dict[str, int]]) -> pd.DataFrame:
    rows = []
    for column in LIKERT_COLUMNS:
        values = [s[column] for s in all_scores if column in s]
        rows.append(
            (
                column,
                "Yes" if column in REVERSED_COLUMNS else "No",
                len(values),
                _mean(values),
                sample_stdev(values),
                statistics.median(values) if values else None,
            )
        )
    return _numeric_table(rows, ITEMS_COLUMNS, ITEMS_COLUMNS[2:])


def _group_of(raw_value: object, variable: GroupVariable) -> str:
    """Return the name of the group row that a raw cell belongs to."""
    number = parse_number(raw_value)
    if _is_empty(raw_value) or _is_unanswered(number):
        return UNANSWERED_GROUP
    if number is None or not number.is_integer():
        return f"{variable.label} code {str(raw_value).strip()}"
    code = int(number)
    return variable.groups.get(code, f"{variable.label} code {code}")


def _unexpected_order(name: str) -> tuple[int, float, str]:
    """Sort numeric codes by value, then any other text."""
    code = parse_number(name.rpartition(" code ")[2])
    if code is None or math.isnan(code):
        return (1, 0.0, name)
    return (0, code, name)


def _group_table(
    variable: GroupVariable,
    rows: list[pd.Series],
    totals: list[tuple[float, float, float] | None],
    issues: list[Issue],
) -> pd.DataFrame:
    """Build one group sheet; only complete participants enter statistics."""
    members: dict[str, list[tuple[float, float, float]]] = {
        name: [] for name in variable.groups.values()
    }
    unexpected = set()
    for row, total in zip(rows, totals):
        raw_value = row[variable.column]
        name = _group_of(raw_value, variable)
        if name not in members:
            members[name] = []
            if name != UNANSWERED_GROUP:
                unexpected.add(name)
        if name in unexpected:
            issues.append(
                Issue(
                    str(row[config.ID_COLUMN]).strip(),
                    None,
                    variable.column,
                    raw_value,
                    f"Unexpected {variable.label} code; shown in its own "
                    "row of the Likert group sheet.",
                )
            )
        if total is not None:
            members[name].append(total)

    names = list(variable.groups.values())
    names += sorted(unexpected, key=_unexpected_order)
    if UNANSWERED_GROUP in members:
        names.append(UNANSWERED_GROUP)

    table = []
    for name in names:
        cumulative = [m[0] for m in members[name]]
        average = [m[1] for m in members[name]]
        table.append(
            (
                name,
                len(cumulative),
                _mean(cumulative),
                sample_stdev(cumulative),
                _mean(average),
                sample_stdev(average),
            )
        )
    return _numeric_table(table, GROUP_COLUMNS, GROUP_COLUMNS[1:])


def calculate_likert(raw: pd.DataFrame) -> LikertResult:
    """Calculate all Likert tables from the raw export.

    Raises:
        InputLayoutError: If an expected column is missing.
    """
    check_layout(raw)
    check_likert_layout(raw)

    rows = select_participants(raw)
    issues: list[Issue] = []
    all_scores = [_score_row(row, issues) for row in rows]
    totals = [_participant_totals(scores) for scores in all_scores]

    scores_table = _numeric_table(
        [
            (str(row[config.ID_COLUMN]).strip(), *(total or (None,) * 3))
            for row, total in zip(rows, totals)
        ],
        SCORES_COLUMNS,
        SCORES_COLUMNS[1:],
    )
    groups = {
        variable.sheet: _group_table(variable, rows, totals, issues)
        for variable in GROUP_VARIABLES
    }
    return LikertResult(
        scores=scores_table,
        items=_items_table(all_scores),
        groups=groups,
        issues=issues,
        participants=len(rows),
        complete=sum(total is not None for total in totals),
        partial=sum(
            0 < len(scores) < len(LIKERT_COLUMNS) for scores in all_scores
        ),
    )

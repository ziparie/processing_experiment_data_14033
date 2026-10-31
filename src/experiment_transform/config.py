"""Settings for reading the Qualtrics export and coding the responses.

Every rule used in the transformation is defined here, so a change in the
coding scheme only needs to be made in one place.
"""

from typing import Final

# --- Input layout --------------------------------------------------------
# Qualtrics exports two header rows: variable codes (row 1) and the question
# text (row 2). Row 1 is used as column names; row 2 is skipped.
QUESTION_TEXT_ROW: Final[int] = 1

ID_COLUMN: Final[str] = "ResponseId"  # Column H in the raw export.

# Only rows from this distribution channel are kept. The comparison ignores
# case and surrounding whitespace. Preview rows are counted separately; any
# other value, including an empty cell, is reported in the validation sheet.
CHANNEL_COLUMN: Final[str] = "DistributionChannel"  # Column I.
INCLUDED_CHANNEL: Final[str] = "anonymous"
PREVIEW_CHANNEL: Final[str] = "preview"

# Any other value in the consent column (2, -99, empty) means no consent.
# Such a respondent is still processed if at least one question was answered,
# and is skipped otherwise.
CONSENT_COLUMN: Final[str] = "Q1"
CONSENT_CODE: Final[int] = 1

# "Are you a student?" -99 or an empty cell means unanswered. Any other code
# is reported in the validation sheet and not counted.
STUDENT_COLUMN: Final[str] = "Q3"
STUDENT_CODE: Final[int] = 1
NOT_STUDENT_CODE: Final[int] = 2

# Qualtrics code for an item that was shown but not answered.
UNANSWERED_CODE: Final[int] = -99

# Which of the four Qualtrics timing measures goes into the Timing column.
# Options: "First Click", "Last Click", "Page Submit", "Click Count".
TIMING_MEASURE: Final[str] = "Page Submit"
TIMING_MEASURES: Final[tuple[str, ...]] = (
    "First Click",
    "Last Click",
    "Page Submit",
    "Click Count",
)

# --- Coding rules --------------------------------------------------------
CORRECT_SCORE: Final[int] = 100
INCORRECT_SCORE: Final[int] = 0

# Tolerance for comparing numeric answers (guards against float noise such
# as 4.999999 vs 5).
ANSWER_TOLERANCE: Final[float] = 1e-9

CONFIDENCE_MIN: Final[float] = 0.0
CONFIDENCE_MAX: Final[float] = 100.0

# "I know this question": raw code -> coded value. An empty cell is coded
# as familiar (see FAMILIAR_IF_EMPTY). Any other code is reported in the
# validation sheet and left missing.
FAMILIAR_CODING: Final[dict[int, int]] = {
    2: 0,
    UNANSWERED_CODE: 0,
    3: 1,
}
FAMILIAR_IF_EMPTY: Final[int] = 1

# --- Output --------------------------------------------------------------
OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    "UserId",
    "Question",
    "Timing",
    "Score",
    "Confidence",
    "Familiar",
)
DATA_SHEET: Final[str] = "Data"
VALIDATION_SHEET: Final[str] = "Validation"
SUMMARY_SHEET: Final[str] = "Summary"

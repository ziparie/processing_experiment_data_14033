"""The nine CRT-style questions and their correct answers.

Each question occupies seven consecutive columns in the Qualtrics export:
four timing columns, the answer, the confidence rating and the
familiarity item. The column codes and correct answers below were taken
from the export header and from the answer key (MeaningOfAnswer.xlsx,
sheet Table13, column C).

Note: the timing blocks are not numbered in order (question 7 uses Q54 and
question 8 uses Q53). This matches the export and is intentional.
"""

from dataclasses import dataclass
from typing import Final

from experiment_transform.config import TIMING_MEASURES


@dataclass(frozen=True)
class Question:
    """Column codes and correct answer of one question.

    Attributes:
        number: Position of the question in the experiment (1-9).
        timing_prefix: Qualtrics code of the timing block, e.g. "Q47".
        answer_column: Column with the numeric answer.
        confidence_column: Column with the 0-100 confidence rating.
        familiar_column: Column with the "I know this question" item.
        correct_answer: The correct numeric answer.
    """

    number: int
    timing_prefix: str
    answer_column: str
    confidence_column: str
    familiar_column: str
    correct_answer: float

    def timing_column(self, measure: str) -> str:
        """Return the column name of one timing measure."""
        return f"{self.timing_prefix}_{measure}"

    @property
    def block_columns(self) -> tuple[str, ...]:
        """All seven columns of the question, in export order."""
        timing = tuple(self.timing_column(m) for m in TIMING_MEASURES)
        return (
            *timing,
            self.answer_column,
            self.confidence_column,
            self.familiar_column,
        )


QUESTIONS: Final[tuple[Question, ...]] = (
    Question(1, "Q47", "Q13_4", "Q14_1", "Q35", 5),  # bat and ball
    Question(2, "Q48", "Q24_4", "Q17_1", "Q36", 5),  # 5 machines
    Question(3, "Q49", "Q25_4", "Q18_1", "Q37", 47),  # lily pads
    Question(4, "Q50", "Q26_4", "Q19_1", "Q38", 4),  # water barrel
    Question(5, "Q51", "Q27_4", "Q20_1", "Q39", 29),  # class rank
    Question(6, "Q52", "Q28_4", "Q21_1", "Q40", 20),  # cow trade
    Question(7, "Q54", "Q30_4", "Q43_1", "Q41", 2),  # race position
    Question(8, "Q53", "Q31_4", "Q22_1", "Q42", 8),  # farmer's sheep
    Question(9, "Q55", "Q32_4", "Q23_1", "Q44", 0),  # hole volume
)

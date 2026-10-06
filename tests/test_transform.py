"""Tests for the transformation (run with ``python -m unittest``)."""

import math
import unittest

import pandas as pd

from experiment_transform import config
from experiment_transform.questions import QUESTIONS
from experiment_transform.transform import (
    InputLayoutError,
    code_confidence,
    code_familiar,
    code_score,
    code_timing,
    transform,
)


def make_export(respondents: list[dict[str, str]]) -> pd.DataFrame:
    """Build a minimal export with every expected column, all empty."""
    columns = [config.ID_COLUMN, config.CONSENT_COLUMN]
    for question in QUESTIONS:
        columns.extend(question.block_columns)
    frame = pd.DataFrame([{c: None for c in columns} for _ in respondents])
    for index, values in enumerate(respondents):
        for column, value in values.items():
            frame.loc[index, column] = value
    return frame


class CodingRulesTest(unittest.TestCase):
    def test_score_correct_wrong_and_unanswered(self):
        self.assertEqual(code_score("5", 5), 100)
        self.assertEqual(code_score("5.0", 5), 100)
        self.assertEqual(code_score("0.05", 5), 0)
        self.assertIsNone(code_score("-99", 5))
        self.assertIsNone(code_score(None, 5))
        self.assertIsNone(code_score("abc", 5))

    def test_score_zero_is_a_valid_answer(self):
        self.assertEqual(code_score("0", 0), 100)

    def test_confidence(self):
        self.assertEqual(code_confidence("92.9"), 92.9)
        self.assertIsNone(code_confidence("-99"))
        self.assertIsNone(code_confidence(""))

    def test_familiar(self):
        self.assertEqual(code_familiar("2"), 0)
        self.assertEqual(code_familiar("-99"), 0)
        self.assertEqual(code_familiar("3"), 1)
        self.assertEqual(code_familiar(None), 1)
        self.assertEqual(code_familiar(""), 1)
        self.assertIsNone(code_familiar("7"))

    def test_timing(self):
        self.assertEqual(code_timing("25.312"), 25.312)
        self.assertIsNone(code_timing(None))


class TransformTest(unittest.TestCase):
    def test_nine_rows_per_respondent(self):
        result = transform(
            make_export(
                [
                    {config.ID_COLUMN: "R_a", config.CONSENT_COLUMN: "1"},
                    {config.ID_COLUMN: "R_b", config.CONSENT_COLUMN: "1"},
                ]
            )
        )
        self.assertEqual(len(result.data), 18)
        self.assertEqual(
            list(result.data.columns), list(config.OUTPUT_COLUMNS)
        )
        self.assertEqual(list(result.data["Question"]), list(range(1, 10)) * 2)

    def test_no_consent_is_skipped(self):
        result = transform(
            make_export(
                [
                    {config.ID_COLUMN: "R_yes", config.CONSENT_COLUMN: "1"},
                    {config.ID_COLUMN: "R_no", config.CONSENT_COLUMN: "2"},
                ]
            )
        )
        self.assertEqual(set(result.data["UserId"]), {"R_yes"})
        self.assertEqual(result.respondents_skipped_no_consent, ["R_no"])

    def test_values_go_to_the_right_question(self):
        q7 = QUESTIONS[6]
        result = transform(
            make_export(
                [
                    {
                        config.ID_COLUMN: "R_a",
                        config.CONSENT_COLUMN: "1",
                        q7.timing_column(config.TIMING_MEASURE): "12.5",
                        q7.answer_column: "2",
                        q7.confidence_column: "80",
                        q7.familiar_column: "3",
                    }
                ]
            )
        )
        row = result.data[result.data["Question"] == 7].iloc[0]
        self.assertEqual(row["Timing"], 12.5)
        self.assertEqual(row["Score"], 100)
        self.assertEqual(row["Confidence"], 80)
        self.assertEqual(row["Familiar"], 1)
        other = result.data[result.data["Question"] == 1].iloc[0]
        self.assertTrue(math.isnan(other["Score"]))

    def test_problems_are_reported(self):
        q1 = QUESTIONS[0]
        result = transform(
            make_export(
                [
                    {
                        config.ID_COLUMN: "R_a",
                        config.CONSENT_COLUMN: "1",
                        q1.confidence_column: "150",
                        q1.familiar_column: "9",
                    }
                ]
            )
        )
        variables = sorted(issue.variable for issue in result.issues)
        self.assertEqual(variables, ["Confidence", "Familiar"])

    def test_missing_column_raises(self):
        export = make_export([{config.ID_COLUMN: "R_a"}])
        with self.assertRaises(InputLayoutError):
            transform(export.drop(columns=[QUESTIONS[3].answer_column]))


if __name__ == "__main__":
    unittest.main()

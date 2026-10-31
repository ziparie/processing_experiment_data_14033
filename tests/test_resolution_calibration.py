"""Tests for the per-person calibration and resolution calculations."""

import tempfile
import unittest

import pandas as pd
from test_transform import make_export, respondent, run_cli

from experiment_transform import resolution_calibration as rc


def person(
    user_id: str, scores: list[float | None], confidences: list[float | None]
) -> pd.DataFrame:
    """Build the Data rows for one person."""
    return pd.DataFrame(
        {
            "UserId": user_id,
            "Score": pd.array(scores, dtype="Float64").astype(float),
            "Confidence": pd.array(confidences, dtype="Float64").astype(float),
        }
    )


def calculate_one(
    scores: list[float | None], confidences: list[float | None]
) -> pd.Series:
    """Return the result row for a single person."""
    return rc.calculate(person("R_a", scores, confidences)).iloc[0]


class GammaTest(unittest.TestCase):
    def test_perfect_positive(self) -> None:
        row = calculate_one([0, 0, 100, 100], [10, 20, 30, 40])
        self.assertEqual(row["Concordant Pairs"], 4)
        self.assertEqual(row["Discordant Pairs"], 0)
        self.assertEqual(row["Gamma"], 1)

    def test_perfect_negative(self) -> None:
        row = calculate_one([100, 100, 0, 0], [10, 20, 30, 40])
        self.assertEqual(row["Gamma"], -1)

    def test_mixed_pairs(self) -> None:
        # Pairs with different scores: 10-20 C, 10-40 C, 20-30 D, 30-40 C.
        row = calculate_one([0, 100, 0, 100], [10, 20, 30, 40])
        self.assertEqual(row["Concordant Pairs"], 3)
        self.assertEqual(row["Discordant Pairs"], 1)
        self.assertEqual(row["Gamma"], 0.5)

    def test_tied_confidence_pairs_are_dropped(self) -> None:
        # Only 50@0 vs 90@100 and 50@100 vs 90@0 differ on both variables.
        row = calculate_one([0, 100, 100, 0], [50, 50, 90, 90])
        self.assertEqual(row["Concordant Pairs"], 1)
        self.assertEqual(row["Discordant Pairs"], 1)
        self.assertEqual(row["Gamma"], 0)
        self.assertTrue(pd.isna(row["Gamma Note"]))

    def test_constant_score_has_no_gamma(self) -> None:
        row = calculate_one([100, 100, 100], [10, 20, 30])
        self.assertTrue(pd.isna(row["Gamma"]))
        self.assertEqual(row["Gamma Note"], rc.EQUAL_SCORES_NOTE)

    def test_constant_confidence_has_no_gamma(self) -> None:
        row = calculate_one([0, 100, 0], [50, 50, 50])
        self.assertTrue(pd.isna(row["Gamma"]))
        self.assertEqual(row["Gamma Note"], rc.EQUAL_CONFIDENCE_NOTE)

    def test_single_question_reports_both_notes(self) -> None:
        row = calculate_one([100], [50])
        self.assertTrue(pd.isna(row["Gamma"]))
        self.assertIn(rc.EQUAL_SCORES_NOTE, row["Gamma Note"])
        self.assertIn(rc.EQUAL_CONFIDENCE_NOTE, row["Gamma Note"])


class CalibrationTest(unittest.TestCase):
    def test_overconfidence(self) -> None:
        row = calculate_one([0, 100], [80, 80])
        self.assertEqual(row["Average Score"], 50)
        self.assertEqual(row["Average Confidence"], 80)
        self.assertEqual(row["Calibration"], 30)
        self.assertEqual(row["Calibration Direction"], rc.OVERCONFIDENCE)

    def test_underconfidence(self) -> None:
        row = calculate_one([100, 100], [60, 80])
        self.assertEqual(row["Calibration"], 30)
        self.assertEqual(row["Calibration Direction"], rc.UNDERCONFIDENCE)

    def test_no_difference(self) -> None:
        row = calculate_one([0, 100], [40, 60])
        self.assertEqual(row["Calibration"], 0)
        self.assertEqual(row["Calibration Direction"], rc.NO_DIFFERENCE)


class MissingValuesTest(unittest.TestCase):
    def test_question_missing_either_value_is_left_out(self) -> None:
        row = calculate_one(
            [0, 100, None, 100], [20, 40, 90, None]
        )
        self.assertEqual(row["Questions Used"], 2)
        self.assertEqual(row["Average Score"], 50)
        self.assertEqual(row["Average Confidence"], 30)
        self.assertEqual(row["Gamma"], 1)

    def test_person_without_pairs_keeps_an_empty_row(self) -> None:
        row = calculate_one([None, 100], [50, None])
        self.assertEqual(row["Questions Used"], 0)
        self.assertTrue(pd.isna(row["Calibration"]))
        self.assertTrue(pd.isna(row["Gamma"]))
        self.assertEqual(row["Gamma Note"], rc.NO_QUESTIONS_NOTE)

    def test_each_person_is_calculated_separately(self) -> None:
        data = pd.concat(
            [
                person("R_b", [0, 100], [10, 20]),
                person("R_a", [0, 100], [20, 10]),
            ]
        )
        table = rc.calculate(data)
        self.assertEqual(table["UserId"].tolist(), ["R_b", "R_a"])
        self.assertEqual(table["Gamma"].tolist(), [1, -1])


class CliTest(unittest.TestCase):
    def test_sheet_is_added_to_the_workbook(self) -> None:
        export = make_export([respondent("R_a", answers=9, confidences=9)])
        with tempfile.TemporaryDirectory() as folder:
            code, _, _, output = run_cli(export, folder)
            self.assertEqual(code, 0)
            sheets = pd.read_excel(output, sheet_name=None)
        self.assertEqual(sheets[rc.SHEET]["UserId"].tolist(), ["R_a"])
        self.assertEqual(sheets[rc.SHEET]["Questions Used"].tolist(), [9])
        self.assertEqual(list(sheets[rc.SHEET].columns), list(rc.COLUMNS))

"""Tests for the correct/incorrect and known/unknown comparison sheets."""

import tempfile
import unittest

import pandas as pd
from test_transform import make_export, respondent, run_cli

from experiment_transform import performance_measures as pm
from experiment_transform import resolution_calibration as rc
from experiment_transform.questions import QUESTIONS


def person(
    user_id: str,
    timings: list[float | None],
    scores: list[float | None],
    confidences: list[float | None],
    familiar: list[int | None],
) -> pd.DataFrame:
    """Build the Data rows for one person."""
    return pd.DataFrame(
        {
            "UserId": user_id,
            "Timing": pd.array(timings, dtype="Float64").astype(float),
            "Score": pd.array(scores, dtype="Float64").astype(float),
            "Confidence": pd.array(confidences, dtype="Float64").astype(float),
            "Familiar": pd.array(familiar, dtype="Float64").astype(float),
        }
    )


class CorrectVsIncorrectTest(unittest.TestCase):
    def test_averages_and_sample_stdev_per_group(self) -> None:
        data = person(
            "R_a",
            [10, 20, 30, 50],
            [100, 100, 0, 0],
            [40, 60, 10, 30],
            [1, 1, 1, 1],
        )
        row = pm.calculate_correct(data).iloc[0]
        self.assertEqual(row["Correct N"], 2)
        self.assertEqual(row["Correct Avg Time"], 15)
        self.assertAlmostEqual(row["Correct Stdev Time"], 50**0.5)
        self.assertEqual(row["Correct Avg Confidence"], 50)
        self.assertAlmostEqual(row["Correct Stdev Confidence"], 200**0.5)
        self.assertEqual(row["Incorrect N"], 2)
        self.assertEqual(row["Incorrect Avg Time"], 40)
        self.assertEqual(row["Incorrect Avg Confidence"], 20)

    def test_one_question_has_no_stdev_and_empty_group_has_no_values(
        self,
    ) -> None:
        data = person("R_a", [10], [100], [40], [1])
        row = pm.calculate_correct(data).iloc[0]
        self.assertEqual(row["Correct Avg Time"], 10)
        self.assertTrue(pd.isna(row["Correct Stdev Time"]))
        self.assertEqual(row["Incorrect N"], 0)
        self.assertTrue(pd.isna(row["Incorrect Avg Time"]))
        self.assertTrue(pd.isna(row["Incorrect Stdev Confidence"]))


class KnownVsUnknownTest(unittest.TestCase):
    def test_groups_follow_familiar_and_include_score(self) -> None:
        data = person(
            "R_a",
            [10, 20, 30, 50],
            [100, 0, 100, 100],
            [40, 60, 10, 30],
            [1, 1, 0, 0],
        )
        row = pm.calculate_known(data).iloc[0]
        self.assertEqual(row["Known N"], 2)
        self.assertEqual(row["Known Avg Score"], 50)
        self.assertAlmostEqual(row["Known Stdev Score"], 5000**0.5)
        self.assertEqual(row["Unknown N"], 2)
        self.assertEqual(row["Unknown Avg Time"], 40)
        self.assertEqual(row["Unknown Avg Score"], 100)
        self.assertEqual(row["Unknown Stdev Score"], 0)

    def test_unexpected_familiar_code_is_in_neither_group(self) -> None:
        data = person("R_a", [10, 20], [100, 0], [40, 60], [1, None])
        row = pm.calculate_known(data).iloc[0]
        self.assertEqual(row["Known N"], 1)
        self.assertEqual(row["Unknown N"], 0)

    def test_unknown_averages_match_the_unknown_calibration_sheet(
        self,
    ) -> None:
        data = person(
            "R_a",
            [10, 20, 30, 40],
            [100, 0, None, 100],
            [40, 60, 10, None],
            [0, 0, 0, 0],
        )
        known = pm.calculate_known(data).iloc[0]
        unknown = rc.calculate_unknown(data).iloc[0]
        self.assertEqual(known["Unknown N"], unknown[rc.UNKNOWN_COUNT])
        self.assertEqual(known["Unknown Avg Score"], unknown["Average Score"])
        self.assertEqual(
            known["Unknown Avg Confidence"], unknown["Average Confidence"]
        )


class OneValueOnlyTest(unittest.TestCase):
    def test_questions_with_one_value_are_counted_and_left_out(self) -> None:
        data = person(
            "R_a",
            [10, 900, 900, 900],
            [100, 100, None, None],
            [50, None, 90, None],
            [1, 1, 1, 1],
        )
        for table in (pm.calculate_correct(data), pm.calculate_known(data)):
            row = table.iloc[0]
            self.assertEqual(row["Only Score"], 1)
            self.assertEqual(row["Only Confidence"], 1)
        row = pm.calculate_correct(data).iloc[0]
        self.assertEqual(row["Correct N"], 1)
        self.assertEqual(row["Correct Avg Time"], 10)
        row = pm.calculate_known(data).iloc[0]
        self.assertEqual(row["Known N"], 1)
        self.assertEqual(row["Known Avg Confidence"], 50)

    def test_each_person_is_calculated_separately(self) -> None:
        data = pd.concat(
            [
                person("R_b", [10], [100], [None], [1]),
                person("R_a", [10], [100], [50], [1]),
            ]
        )
        table = pm.calculate_known(data)
        self.assertEqual(table["UserId"].tolist(), ["R_b", "R_a"])
        self.assertEqual(table["Only Score"].tolist(), [1, 0])


class CliTest(unittest.TestCase):
    def test_sheets_are_added_after_the_calibration_sheets(self) -> None:
        # Question 1 is marked unknown; empty familiarity cells count as known.
        export = make_export(
            [
                respondent(
                    "R_a",
                    answers=9,
                    confidences=8,
                    **{QUESTIONS[0].familiar_column: "2"},
                )
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            code, _, _, output = run_cli(export, folder)
            self.assertEqual(code, 0)
            sheets = pd.read_excel(output, sheet_name=None)
        names = list(sheets)
        start = names.index(rc.SHEET)
        self.assertEqual(
            names[start : start + 4],
            [rc.SHEET, rc.UNKNOWN_SHEET, pm.CORRECT_SHEET, pm.KNOWN_SHEET],
        )
        self.assertEqual(sheets[rc.UNKNOWN_SHEET][rc.UNKNOWN_COUNT][0], 1)
        known = sheets[pm.KNOWN_SHEET].iloc[0]
        self.assertEqual(known["Known N"], 7)
        self.assertEqual(known["Unknown N"], 1)
        self.assertEqual(known["Only Score"], 1)
        correct = sheets[pm.CORRECT_SHEET].iloc[0]
        self.assertEqual(correct["Correct N"] + correct["Incorrect N"], 8)

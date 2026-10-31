"""Tests for the Likert index sheets."""

import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from test_transform import make_export, respondent, run_cli

from experiment_transform import config
from experiment_transform.likert import (
    GROUP_COLUMNS,
    ITEMS_COLUMNS,
    ITEMS_SHEET,
    GROUP_VARIABLES,
    LIKERT_COLUMNS,
    SCORES_COLUMNS,
    SCORES_SHEET,
    calculate_likert,
    parse_answer,
    sample_stdev,
    score_item,
)
from experiment_transform.likert_output import append_likert_sheets
from experiment_transform.transform import (
    InputLayoutError,
    transform,
    write_excel,
)

GENDER = "Likert by Gender"
STUDENT = "Likert by Student"
AGE = "Likert by Age"
DEGREE = "Likert by Degree"


def answers(*values: str | None) -> dict[str, str | None]:
    """Map values to the items in the order Q47, Q48, ... Q52."""
    ordered = ("Q47", "Q48", "Q49", "Q50", "Q51", "Q52")
    return dict(zip(ordered, values))


def person(user_id: str, *values: str | None, **cells: str) -> dict:
    """Build a consenting respondent with Likert answers and other cells."""
    return respondent(user_id, **answers(*values), **cells)


def calculate(*people: dict):
    return calculate_likert(make_export(list(people)))


def group_row(table: pd.DataFrame, name: str) -> pd.Series:
    return table[table["Group"] == name].iloc[0]


class ScoringTest(unittest.TestCase):
    def test_reversal_only_on_q50_and_q51(self):
        for column in ("Q50", "Q51"):
            self.assertEqual(score_item(column, 1), 5)
            self.assertEqual(score_item(column, 5), 1)
        for column in ("Q47", "Q48", "Q49", "Q52"):
            self.assertEqual(score_item(column, 2), 2)

    def test_parse_answer(self):
        self.assertEqual(parse_answer("1"), 1)
        self.assertEqual(parse_answer(" 5.0 "), 5)
        for value in ("0", "6", "3.5", "-99", "abc", "", None, "inf", "nan"):
            with self.subTest(value=value):
                self.assertIsNone(parse_answer(value))

    def test_sample_stdev(self):
        self.assertIsNone(sample_stdev([]))
        self.assertIsNone(sample_stdev([3.0]))
        self.assertEqual(sample_stdev([3.0, 3.0]), 0)
        self.assertAlmostEqual(sample_stdev([1.0, 2.0, 3.0]), 1.0)


class ParticipantScoresTest(unittest.TestCase):
    def test_scores_use_reversed_items(self):
        result = calculate(person("R_a", "5", "4", "3", "1", "2", "3"))
        row = result.scores.iloc[0]
        # Scores after reversal: 5, 4, 3, 5, 4, 3.
        self.assertEqual(row["Cumulative"], 24)
        self.assertEqual(row["Average"], 4)
        self.assertAlmostEqual(row["Stdev"], math.sqrt(0.8))
        self.assertEqual(list(result.scores.columns), list(SCORES_COLUMNS))
        self.assertEqual(result.issues, [])

    def test_identical_scores_have_stdev_zero_not_empty(self):
        result = calculate(person("R_a", "3", "3", "3", "3", "3", "3"))
        row = result.scores.iloc[0]
        self.assertEqual(row["Cumulative"], 18)
        self.assertEqual(row["Stdev"], 0)

    def test_extreme_cumulative_scores(self):
        result = calculate(
            person("R_low", "1", "1", "1", "5", "5", "1"),
            person("R_high", "5", "5", "5", "1", "1", "5"),
        )
        self.assertEqual(list(result.scores["Cumulative"]), [6, 30])

    def test_partial_answers_are_empty_listed_and_left_out_of_groups(self):
        result = calculate(
            person("R_full", "5", "5", "5", "1", "1", "5", Q6="1"),
            person("R_part", "1", "-99", "1", "5", "5", "1", Q6="1"),
        )
        row = result.scores[result.scores["UserId"] == "R_part"].iloc[0]
        for column in ("Cumulative", "Average", "Stdev"):
            self.assertTrue(math.isnan(row[column]))
        self.assertEqual(
            [(i.user_id, i.variable) for i in result.issues],
            [("R_part", "Likert")],
        )
        self.assertEqual(result.complete, 1)
        self.assertEqual(result.partial, 1)

        arts = group_row(result.groups[DEGREE], "ArtHumanities")
        self.assertEqual(arts["N"], 1)
        self.assertEqual(arts["Cumulative Average"], 30)

        # Valid answers of the partial participant still count per item.
        items = result.items.set_index("Question")
        self.assertEqual(items.loc["Q47", "N"], 2)
        self.assertEqual(items.loc["Q47", "Average"], 3)
        self.assertEqual(items.loc["Q48", "N"], 1)
        self.assertEqual(items.loc["Q50", "Average"], 3)

    def test_no_answers_is_empty_but_not_listed(self):
        result = calculate(person("R_a"))
        self.assertEqual(len(result.scores), 1)
        self.assertTrue(math.isnan(result.scores.iloc[0]["Cumulative"]))
        self.assertEqual(result.partial, 0)
        self.assertEqual(result.issues, [])


class MissingAndInvalidTest(unittest.TestCase):
    def test_only_non_empty_invalid_values_are_listed(self):
        for value, listed in (
            ("-99", False),
            ("", False),
            (None, False),
            ("7", True),
            ("0", True),
            ("2.5", True),
            ("abc", True),
        ):
            with self.subTest(value=value):
                result = calculate(
                    person("R_a", value, "1", "1", "1", "1", "1")
                )
                invalid = [i for i in result.issues if i.variable == "Q47"]
                self.assertEqual(len(invalid), int(listed))
                # Missing or invalid, the participant is partial either way.
                self.assertTrue(
                    math.isnan(result.scores.iloc[0]["Cumulative"])
                )
                self.assertEqual(
                    [i.variable for i in result.issues].count("Likert"), 1
                )
                self.assertEqual(result.items.iloc[0]["N"], 0)


class ItemsTest(unittest.TestCase):
    def test_statistics_after_reversal(self):
        result = calculate(
            person("R_a", "1", "1", "1", "1", "1", "1"),
            person("R_b", "2", "2", "2", "2", "2", "2"),
            person("R_c", "4", "4", "4", "4", "4", "4"),
        )
        self.assertEqual(list(result.items.columns), list(ITEMS_COLUMNS))
        self.assertEqual(list(result.items["Question"]), list(LIKERT_COLUMNS))
        items = result.items.set_index("Question")
        self.assertEqual(items.loc["Q47", "Reversed"], "No")
        self.assertEqual(items.loc["Q47", "N"], 3)
        self.assertAlmostEqual(items.loc["Q47", "Average"], 7 / 3)
        self.assertAlmostEqual(
            items.loc["Q47", "Stdev"], math.sqrt(7 / 3)
        )
        self.assertEqual(items.loc["Q47", "Median"], 2)
        # Q50 scores are 5, 4, 2.
        self.assertEqual(items.loc["Q50", "Reversed"], "Yes")
        self.assertAlmostEqual(items.loc["Q50", "Average"], 11 / 3)
        self.assertEqual(items.loc["Q50", "Median"], 4)

    def test_single_answer_has_no_stdev(self):
        result = calculate(person("R_a", "2", "2", "2", "2", "2", "2"))
        row = result.items.iloc[0]
        self.assertEqual(row["N"], 1)
        self.assertEqual(row["Average"], 2)
        self.assertTrue(math.isnan(row["Stdev"]))


class GroupsTest(unittest.TestCase):
    def test_group_definitions_use_configured_columns_and_labels(self):
        definitions = {group.column: group for group in GROUP_VARIABLES}
        expected = {
            config.GENDER_COLUMN: config.GENDER_GROUPS,
            config.STUDENT_COLUMN: {
                config.STUDENT_CODE: "Yes",
                config.NOT_STUDENT_CODE: "No",
            },
            config.AGE_COLUMN: config.AGE_GROUPS,
            config.DEGREE_COLUMN: config.DEGREE_GROUPS,
        }
        self.assertEqual(
            {column: group.groups for column, group in definitions.items()},
            expected,
        )
        self.assertEqual(
            tuple(definitions),
            (
                config.GENDER_COLUMN,
                config.STUDENT_COLUMN,
                config.AGE_COLUMN,
                config.DEGREE_COLUMN,
            ),
        )

    def test_every_label_is_listed_in_code_order(self):
        result = calculate(person("R_a", "3", "3", "3", "3", "3", "3"))
        expected = {
            GENDER: ["Male", "Female", "A-binary", "Gender code 4"],
            STUDENT: ["Yes", "No"],
            AGE: ["18-25", "26-35", "36-45", "46-50"],
            DEGREE: [
                "ArtHumanities",
                "SocialSciences",
                "NaturalSciences",
                "ExactSciences",
            ],
        }
        for sheet, labels in expected.items():
            with self.subTest(sheet):
                table = result.groups[sheet]
                # This participant has every group column empty.
                self.assertEqual(list(table["Group"]), [*labels, "Unanswered"])
                self.assertEqual(list(table.columns), list(GROUP_COLUMNS))

    def test_each_variable_uses_its_own_column(self):
        result = calculate(
            person(
                "R_a",
                "3", "3", "3", "3", "3", "3",
                Q5="4", Q3="2", Q4="3", Q6="2",
            ),
        )
        for sheet, name in (
            (GENDER, "Gender code 4"),
            (STUDENT, "No"),
            (AGE, "36-45"),
            (DEGREE, "SocialSciences"),
        ):
            with self.subTest(sheet):
                table = result.groups[sheet]
                self.assertEqual(group_row(table, name)["N"], 1)
                self.assertNotIn("Unanswered", list(table["Group"]))
        self.assertEqual(result.issues, [])

    def test_degree_statistics(self):
        result = calculate(
            # Cumulative 18, average 3.
            person("R_a", "3", "3", "3", "3", "3", "3", Q6="3"),
            # Cumulative 30, average 5.
            person("R_b", "5", "5", "5", "1", "1", "5", Q6="3"),
            # Cumulative 6, average 1: a group of one.
            person("R_c", "1", "1", "1", "5", "5", "1", Q6="4"),
        )
        table = result.groups[DEGREE]

        pair = group_row(table, "NaturalSciences")
        self.assertEqual(pair["N"], 2)
        self.assertEqual(pair["Cumulative Average"], 24)
        self.assertAlmostEqual(pair["Cumulative Stdev"], math.sqrt(72))
        self.assertEqual(pair["Average Average"], 4)
        self.assertAlmostEqual(pair["Average Stdev"], math.sqrt(2))

        one = group_row(table, "ExactSciences")
        self.assertEqual(one["N"], 1)
        self.assertEqual(one["Cumulative Average"], 6)
        self.assertEqual(one["Average Average"], 1)
        self.assertTrue(math.isnan(one["Cumulative Stdev"]))
        self.assertTrue(math.isnan(one["Average Stdev"]))

        empty = group_row(table, "ArtHumanities")
        self.assertEqual(empty["N"], 0)
        for column in GROUP_COLUMNS[2:]:
            self.assertTrue(math.isnan(empty[column]))

    def test_unanswered_row_for_empty_and_minus_99(self):
        result = calculate(
            person("R_a", "3", "3", "3", "3", "3", "3", Q6="-99"),
            person("R_b", "3", "3", "3", "3", "3", "3", Q6="  "),
        )
        row = group_row(result.groups[DEGREE], "Unanswered")
        self.assertEqual(row["N"], 2)
        self.assertEqual(result.issues, [])

    def test_unanswered_row_appears_for_someone_without_scores(self):
        result = calculate(person("R_a"))
        row = group_row(result.groups[DEGREE], "Unanswered")
        self.assertEqual(row["N"], 0)

    def test_unexpected_codes_get_own_rows_and_are_listed(self):
        result = calculate(
            person("R_a", "3", "3", "3", "3", "3", "3", Q6="9"),
            person("R_b", "3", "3", "3", "3", "3", "3", Q6="9.0"),
            person("R_c", "3", "3", "3", "3", "3", "3", Q6="5"),
            person("R_d", "3", "3", "3", "3", "3", "3", Q6="abc"),
            person("R_e", "3", "3", "3", "3", "3", "3", Q6="-99"),
        )
        table = result.groups[DEGREE]
        self.assertEqual(
            list(table["Group"])[4:],
            [
                "Degree code 5",
                "Degree code 9",
                "Degree code abc",
                "Unanswered",
            ],
        )
        self.assertEqual(group_row(table, "Degree code 9")["N"], 2)
        self.assertEqual(
            [i.user_id for i in result.issues if i.variable == "Q6"],
            ["R_a", "R_b", "R_c", "R_d"],
        )


class WhoIsIncludedTest(unittest.TestCase):
    def test_participants_match_the_data_sheet(self):
        likert = answers("3", "3", "3", "3", "3", "3")
        export = make_export(
            [
                respondent("R_ok", **likert),
                respondent("R_case", DistributionChannel=" ANONymous "),
                respondent("R_late", "2", answers=1, **likert),
                respondent("R_likert_only", "2", **likert),
                respondent(
                    "R_preview", DistributionChannel="preview", **likert
                ),
                respondent("R_mail", DistributionChannel="email", **likert),
            ]
        )
        result = calculate_likert(export)
        self.assertEqual(
            list(result.scores["UserId"]), ["R_ok", "R_case", "R_late"]
        )
        self.assertEqual(
            set(result.scores["UserId"]),
            set(transform(export).data["UserId"]),
        )
        self.assertEqual(result.items.iloc[0]["N"], 2)
        self.assertEqual(result.issues, [])

    def test_row_without_id_is_left_out(self):
        result = calculate(respondent(None))
        self.assertTrue(result.scores.empty)


class LayoutTest(unittest.TestCase):
    def test_missing_columns_raise(self):
        export = make_export([respondent("R_a")])
        for column in (*LIKERT_COLUMNS, "Q3", "Q4", "Q5", "Q6"):
            with self.subTest(column=column):
                with self.assertRaisesRegex(InputLayoutError, column):
                    calculate_likert(export.drop(columns=[column]))

    def test_cli_reports_missing_column(self):
        export = make_export([respondent("R_a")]).drop(columns=["Q6"])
        with tempfile.TemporaryDirectory() as folder:
            code, _, stderr, output = run_cli(export, folder)
            self.assertFalse(output.exists())
        self.assertEqual(code, 1)
        self.assertIn("'Q6'", stderr)


class ZeroRowsTest(unittest.TestCase):
    def test_all_sheets_are_written_with_headers(self):
        export = make_export(
            [respondent("R_a", DistributionChannel="preview")]
        )
        result = transform(export)
        likert = calculate_likert(export)
        self.assertEqual(likert.participants, 0)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.xlsx"
            write_excel(result, path)
            append_likert_sheets(likert, path)
            sheets = pd.read_excel(path, sheet_name=None)

        self.assertEqual(
            list(sheets),
            [
                config.DATA_SHEET,
                config.SUMMARY_SHEET,
                config.VALIDATION_SHEET,
                SCORES_SHEET,
                ITEMS_SHEET,
                GENDER,
                STUDENT,
                AGE,
                DEGREE,
            ],
        )
        self.assertTrue(sheets[SCORES_SHEET].empty)
        self.assertEqual(
            list(sheets[SCORES_SHEET].columns), list(SCORES_COLUMNS)
        )
        # Items and labelled groups are still listed, with N = 0.
        self.assertEqual(list(sheets[ITEMS_SHEET]["N"]), [0] * 6)
        self.assertEqual(list(sheets[DEGREE]["N"]), [0] * 4)
        self.assertEqual(list(sheets[DEGREE].columns), list(GROUP_COLUMNS))


class CliTest(unittest.TestCase):
    def test_sheets_and_validation_reach_the_workbook(self):
        export = make_export(
            [
                person("R_a", "3", "3", "3", "3", "3", "3", Q6="9"),
                person("R_b", "8", "3", "3", "3", "3", "3", Q6="1"),
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            code, stdout, _, output = run_cli(export, folder)
            sheets = pd.read_excel(output, sheet_name=None)
        self.assertEqual(code, 0)
        self.assertEqual(
            list(sheets)[:3],
            [
                config.DATA_SHEET,
                config.SUMMARY_SHEET,
                config.VALIDATION_SHEET,
            ],
        )
        self.assertEqual(len(sheets), 9)
        self.assertEqual(
            sorted(sheets[config.VALIDATION_SHEET]["variable"]),
            ["Likert", "Q47", "Q6"],
        )
        self.assertEqual(sheets[SCORES_SHEET]["Cumulative"][0], 18)
        self.assertRegex(stdout, r"Likert participants:\s+2")
        self.assertRegex(stdout, r"Likert complete:\s+1")
        self.assertRegex(stdout, r"Likert partial:\s+1")
        summary = sheets[config.SUMMARY_SHEET].set_index("Item")["Value"]
        self.assertEqual(summary["Issues reported"], 3)


if __name__ == "__main__":
    unittest.main()

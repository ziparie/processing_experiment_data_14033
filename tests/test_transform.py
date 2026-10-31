"""Tests for the transformation (run with ``python -m unittest``)."""

import contextlib
import io
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from experiment_transform import config
from experiment_transform.cli import main
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
    """Build a minimal export with every expected column.

    Cells are empty except the channel, which defaults to anonymous.
    """
    columns = [
        config.ID_COLUMN,
        config.CHANNEL_COLUMN,
        config.CONSENT_COLUMN,
        config.STUDENT_COLUMN,
    ]
    for question in QUESTIONS:
        columns.extend(question.block_columns)
    frame = pd.DataFrame(
        [{c: None for c in columns} for _ in respondents], columns=columns
    )
    frame[config.CHANNEL_COLUMN] = config.INCLUDED_CHANNEL
    for index, values in enumerate(respondents):
        for column, value in values.items():
            frame.loc[index, column] = value
    return frame


def respondent(
    user_id: str,
    consent: str | None = "1",
    answers: int = 0,
    confidences: int = 0,
    **columns: str | None,
) -> dict[str, str | None]:
    """Build one respondent with the first questions filled in.

    Args:
        user_id: The ResponseId.
        consent: Value of the consent column.
        answers: How many questions get an answer, counted from the first.
        confidences: How many questions get a confidence rating.
        **columns: Any other cell, by column name.

    Returns:
        A mapping of column name to cell value, for make_export.
    """
    values = {config.ID_COLUMN: user_id, config.CONSENT_COLUMN: consent}
    for question in QUESTIONS[:answers]:
        values[question.answer_column] = "7"
    for question in QUESTIONS[:confidences]:
        values[question.confidence_column] = "50"
    values.update(columns)
    return values


def run_cli(frame: pd.DataFrame, folder: str) -> tuple[int, str, str, Path]:
    """Save an export to Excel and run the CLI on it.

    Args:
        frame: The export, without the question text row.
        folder: Directory for the input and output files.

    Returns:
        The exit code, stdout, stderr and the output path.
    """
    text_row = pd.DataFrame([{c: "text" for c in frame.columns}])
    source = Path(folder) / "export.xlsx"
    pd.concat([text_row, frame]).to_excel(source, index=False)
    output = Path(folder) / "out.xlsx"
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = main([str(source), "-o", str(output)])
    return code, stdout.getvalue(), stderr.getvalue(), output


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


class ChannelFilterTest(unittest.TestCase):
    def test_only_anonymous_rows_are_kept(self):
        channels = {
            "R_plain": "anonymous",
            "R_case": "ANONymous",
            "R_space": "  anonymous \t",
            "R_preview": "preview",
            "R_preview_case": " Preview ",
        }
        result = transform(
            make_export(
                [
                    respondent(user_id, DistributionChannel=channel)
                    for user_id, channel in channels.items()
                ]
            )
        )
        self.assertEqual(
            set(result.data["UserId"]), {"R_plain", "R_case", "R_space"}
        )
        self.assertEqual(result.excluded_preview, 2)
        self.assertEqual(result.excluded_other_channel, 0)
        self.assertEqual(result.issues, [])

    def test_unexpected_and_empty_channels_are_reported(self):
        result = transform(
            make_export(
                [
                    respondent("R_ok"),
                    respondent("R_email", DistributionChannel="email"),
                    respondent("R_none", DistributionChannel=None),
                    respondent("R_blank", DistributionChannel="  "),
                ]
            )
        )
        self.assertEqual(set(result.data["UserId"]), {"R_ok"})
        self.assertEqual(result.excluded_other_channel, 3)
        self.assertEqual(result.excluded_preview, 0)
        self.assertEqual(
            [issue.user_id for issue in result.issues],
            ["R_email", "R_none", "R_blank"],
        )
        self.assertEqual(
            {issue.variable for issue in result.issues},
            {config.CHANNEL_COLUMN},
        )

    def test_filter_runs_before_the_consent_logic(self):
        result = transform(
            make_export(
                [respondent("R_a", "2", DistributionChannel="preview")]
            )
        )
        self.assertEqual(result.excluded_preview, 1)
        self.assertEqual(result.respondents_skipped_no_consent, [])

    def test_missing_columns_raise(self):
        export = make_export([respondent("R_a")])
        for column in (config.CHANNEL_COLUMN, config.STUDENT_COLUMN):
            with self.subTest(column=column):
                with self.assertRaisesRegex(InputLayoutError, column):
                    transform(export.drop(columns=[column]))


class ConsentRuleTest(unittest.TestCase):
    def test_non_consent_with_answers_is_processed(self):
        for code in ("2", "-99", None):
            with self.subTest(code=code):
                result = transform(
                    make_export([respondent("R_a", code, answers=1)])
                )
                self.assertEqual(len(result.data), 9)
                self.assertEqual(result.respondents_without_consent, ["R_a"])
                self.assertEqual(result.respondents_skipped_no_consent, [])

    def test_non_consent_without_answers_is_skipped(self):
        answer = QUESTIONS[0].answer_column
        cases = {
            "nothing": respondent("R_a", "2"),
            "minus_99": respondent("R_a", "-99", **{answer: "-99"}),
            "empty_q1": respondent("R_a", None),
            "only_confidence": respondent("R_a", "2", confidences=1),
            "text": respondent("R_a", "2", **{answer: "abc"}),
        }
        for name, values in cases.items():
            with self.subTest(name):
                result = transform(make_export([values]))
                self.assertTrue(result.data.empty)
                self.assertEqual(
                    result.respondents_skipped_no_consent, ["R_a"]
                )
                self.assertEqual(result.respondents_without_consent, [])

    def test_consent_without_answers_is_written(self):
        result = transform(make_export([respondent("R_a", "1")]))
        self.assertEqual(result.respondents_written, 1)
        self.assertEqual(result.respondents_without_consent, [])


class CountsTest(unittest.TestCase):
    def test_answered_all_boundary(self):
        last = QUESTIONS[-1]
        cases = {
            "nine": (respondent("R_a", answers=9, confidences=9), True),
            "eight": (respondent("R_a", answers=8, confidences=9), False),
            "answer_minus_99": (
                respondent(
                    "R_a",
                    answers=9,
                    confidences=9,
                    **{last.answer_column: "-99"},
                ),
                False,
            ),
            "confidence_minus_99": (
                respondent(
                    "R_a",
                    answers=9,
                    confidences=9,
                    **{last.confidence_column: "-99"},
                ),
                False,
            ),
            "missing_confidence": (
                respondent("R_a", answers=9, confidences=8),
                False,
            ),
            "valid_zeros": (
                respondent(
                    "R_a",
                    answers=9,
                    confidences=9,
                    **{last.answer_column: "0", last.confidence_column: "0"},
                ),
                True,
            ),
        }
        for name, (values, expected) in cases.items():
            with self.subTest(name):
                result = transform(make_export([values]))
                self.assertEqual(len(result.answered_all_ids), int(expected))

    def test_answered_all_includes_non_consent(self):
        result = transform(
            make_export([respondent("R_a", "2", answers=9, confidences=9)])
        )
        self.assertEqual(result.answered_all_ids, {"R_a"})

    def test_student_counts(self):
        complete = {"answers": 9, "confidences": 9}
        result = transform(
            make_export(
                [
                    respondent("R_full_yes", Q3="1", **complete),
                    respondent("R_full_no", Q3="2", **complete),
                    respondent("R_part_yes", Q3="1"),
                    respondent("R_part_no", Q3="2"),
                    respondent("R_minus_99", Q3="-99"),
                    respondent("R_empty", Q3=None),
                    respondent(
                        "R_preview",
                        Q3="1",
                        DistributionChannel="preview",
                        **complete,
                    ),
                    respondent("R_skipped", "2", Q3="1"),
                ]
            )
        )
        self.assertEqual(len(result.answered_all_ids), 2)
        self.assertEqual(result.student_ids, {"R_full_yes", "R_part_yes"})
        self.assertEqual(result.students_answered_all, 1)
        self.assertEqual(
            result.student_unanswered_ids, {"R_minus_99", "R_empty"}
        )
        self.assertEqual(result.issues, [])

    def test_unexpected_student_code_is_reported(self):
        result = transform(make_export([respondent("R_a", Q3="5")]))
        self.assertEqual(result.student_ids, set())
        self.assertEqual(result.student_unanswered_ids, set())
        self.assertEqual(
            [issue.variable for issue in result.issues],
            [config.STUDENT_COLUMN],
        )


class CliTest(unittest.TestCase):
    def test_no_anonymous_rows_stops_without_a_file(self):
        export = make_export(
            [
                respondent("R_a", DistributionChannel="preview"),
                respondent("R_b", DistributionChannel="email"),
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            code, stdout, stderr, output = run_cli(export, folder)
            self.assertFalse(output.exists())
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("anonymous: 0", stderr)
        self.assertIn("preview: 1", stderr)
        self.assertIn("other channel: 1", stderr)

    def test_only_skipped_respondents_stops_without_a_file(self):
        export = make_export([respondent("R_a", "2")])
        with tempfile.TemporaryDirectory() as folder:
            code, _, stderr, output = run_cli(export, folder)
            self.assertFalse(output.exists())
        self.assertEqual(code, 1)
        self.assertIn("anonymous: 1", stderr)

    def test_counts_reach_console_and_summary(self):
        export = make_export(
            [
                respondent("R_all", Q3="1", answers=9, confidences=9),
                respondent("R_late", "-99", Q3="2", answers=1),
                respondent("R_skip", "2"),
                respondent("R_prev", DistributionChannel="preview"),
                respondent("R_mail", DistributionChannel="email"),
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            code, stdout, _, output = run_cli(export, folder)
            summary = pd.read_excel(
                output, sheet_name=config.SUMMARY_SHEET, index_col="Item"
            )["Value"]
            issues = pd.read_excel(output, sheet_name=config.VALIDATION_SHEET)
        self.assertEqual(code, 0)

        report = [line.split() for line in stdout.splitlines()]
        self.assertEqual(
            [words[-1] for words in report[:10]],
            ["5", "1", "1", "1", "1", "2", "1", "1", "1", "0"],
        )
        starts = {line.rindex(" ") for line in stdout.splitlines()[:10]}
        self.assertEqual(len(starts), 1)

        self.assertEqual(summary["Excluded: preview"], 1)
        self.assertEqual(summary["Excluded: other channel"], 1)
        self.assertEqual(summary["Skipped: no consent and no answers"], 1)
        self.assertEqual(summary["Skipped IDs"], "R_skip")
        self.assertEqual(
            summary["Processed without consent (has answers)"], 1
        )
        self.assertEqual(summary["Processed without consent IDs"], "R_late")
        self.assertEqual(summary["Answered all questions"], 1)
        self.assertEqual(summary["Students (of respondents written)"], 1)
        self.assertEqual(summary["Students (of answered all)"], 1)
        self.assertEqual(summary["Student question unanswered"], 0)
        self.assertEqual(list(issues["user_id"]), ["R_mail"])


if __name__ == "__main__":
    unittest.main()

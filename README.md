# processing_experiment_data_14033

Turns the raw Qualtrics export of the experiment into analysis-ready
files. The first output is a long-format table for computing
**resolution** and **calibration**.

## What it produces

One Excel workbook with these sheets, followed by the Likert sheets:

| Sheet | Content |
|---|---|
| `Data` | One row per respondent per question (9 rows per respondent) |
| `Summary` | Counts, skipped and non-consenting respondents, coding settings used |
| `Validation` | Every value that could not be coded or looks suspicious |
| `Resolution Calibration` | Calibration and resolution for each person |
| `calibration-resolution-unknown` | The same, using only the questions the person did not know |
| `Correct vs Incorrect` | Each person's time and confidence for correct and incorrect answers |
| `Known vs Unknown` | Each person's time, confidence and score for known and unknown questions |

### `Data` columns

| Column | Meaning | Coding |
|---|---|---|
| `UserId` | Qualtrics `ResponseId` (column H) | copied |
| `Question` | Question number 1–9 in presentation order | — |
| `Timing` | Seconds on the question page | `Page Submit` timing (see `config.TIMING_MEASURE`) |
| `Score` | Accuracy | 100 = correct, 0 = wrong, empty = unanswered (-99) |
| `Confidence` | Confidence rating 0–100 | copied; empty = unanswered (-99) |
| `Familiar` | "I know this question" | 2 or -99 → 0; 3 or empty → 1 |

### Which respondents are written

1. **Channel filter.** Only rows with `DistributionChannel` (column I) equal
   to `anonymous` are kept, ignoring case and surrounding whitespace.
   `preview` rows are counted as excluded. Any other value, including an
   empty cell, is excluded, counted as "other channel" and reported in
   `Validation`.
2. **Consent rule.** `Q1 = 1` means consent; anything else (2, -99 or empty)
   means no consent. A non-consenting respondent with at least one answer
   (a numeric value other than -99 in one of the 9 answer columns) is
   still processed and appears in `Data`. Confidence ratings alone do not
   count as an answer. A non-consenting respondent with no answers is
   skipped. `Summary` lists the count and IDs of both groups.

If no respondents remain, the program prints the channel counts to stderr,
exits with code 1 and writes no file.

### End-of-run counts

The console and `Summary` show the counts below, calculated over the
respondents written to `Data`:

| Count | Meaning |
|---|---|
| Answered all questions | For all 9 questions, the answer and the confidence are numeric and not -99. A valid 0 counts. Familiarity, demographics, the thinking-style items and `Finished` do not count |
| Students | `Q3 = 1`, among all respondents written and among those who answered all questions |
| Student question unanswered | `Q3` is -99 or empty |

Any `Q3` value other than 1, 2, -99 or empty is reported in `Validation`
and not counted.

### `Resolution Calibration` columns

Each person's values use only the questions in `Data` that have both a
`Score` and a `Confidence`. All such questions count, whatever their
`Familiar` value.

| Column | Meaning |
|---|---|
| `Questions Used` | Number of questions with both values |
| `Average Score`, `Average Confidence` | Averages over those questions, both on a 0–100 scale |
| `Calibration` | Absolute difference between the two averages |
| `Calibration Direction` | `Overconfidence` if average confidence is higher, `Underconfidence` if lower, `None` if equal |
| `Concordant Pairs`, `Discordant Pairs` | Question pairs ordered the same way (C) or opposite ways (D) on score and confidence; ties are dropped |
| `Gamma` | Resolution: Goodman-Kruskal gamma, (C − D) / (C + D) |
| `Gamma Note` | Why `Gamma` is empty, which happens when all scores or all confidence ratings are equal |

`Gamma` matches `CROSSTABS /TABLES=success BY JOL BY student
/STATISTICS=GAMMA` in SPSS, with `Score` as `success`, `Confidence` as `JOL`
and `UserId` as `student`.

### `calibration-resolution-unknown` columns

The same columns and calculations as `Resolution Calibration`, using only
questions with `Familiar` = 0. `Questions Used` is named
`Unknown Answers Used`. A person with no such questions keeps a row with a
count of 0, empty values and a `Gamma Note`.

### `Correct vs Incorrect` and `Known vs Unknown` columns

Both sheets have one row per person and use only questions with both a
`Score` and a `Confidence`. Correct means `Score` = 100 and incorrect means
`Score` = 0; known means `Familiar` = 1 and unknown means `Familiar` = 0. A
question with an unexpected `Familiar` code is in neither group.

| Column | Meaning |
|---|---|
| `Only Score`, `Only Confidence` | Questions left out because they have only that value, out of all the person's questions |
| `<Group> N` | Questions in the group, where the groups are `Correct`/`Incorrect` or `Known`/`Unknown` |
| `<Group> Avg Time`, `<Group> Stdev Time` | From `Timing`, ignoring an empty `Timing` |
| `<Group> Avg Confidence`, `<Group> Stdev Confidence` | From `Confidence` |
| `<Group> Avg Score`, `<Group> Stdev Score` | From `Score`, in `Known vs Unknown` only |

Stdev is the sample stdev (n-1): one question gives an empty stdev, and an
empty group gives empty values.

## Likert index sheets

Six more sheets follow the sheets above in the same workbook. They cover
exactly the respondents in `Data`, so a respondent with no consent and no
answers to the 9 questions stays out even if they answered the Likert items.
Column names and group labels are in `config.py`; calculations are in
`likert.py`.

| Sheet | Content |
|---|---|
| `Likert Scores` | One row per participant: `UserId`, cumulative score (6–30), average and stdev of their 6 items |
| `Likert Items` | One row per item: `Question`, `Reversed`, `N`, average, stdev and median of the scores after reversal |
| `Likert by Gender` | Column `Q5` (export column Q): Male, Female, A-binary, Gender code 4 (no label in the answer key) |
| `Likert by Student` | Column `Q3`: Yes, No |
| `Likert by Age` | Column `Q4` (export column P): 18-25, 26-35, 36-45, 46-50 |
| `Likert by Degree` | Column `Q6` (export column R): ArtHumanities, SocialSciences, NaturalSciences, ExactSciences |

Each group sheet shows `Group`, `N`, and the average and stdev of the
participants' cumulative scores and of their average scores.

- **Items.** `Q47, Q52, Q51, Q50, Q49, Q48`, scale 1–5. `Q50` and `Q51` are
  reverse-scored (score = 6 - answer).
- **Missing values.** Anything other than an integer 1–5 is missing. A
  non-empty value other than -99 is also reported in `Validation`.
- **Partial answers.** A participant with some items missing has empty
  cumulative, average and stdev, is reported in `Validation` and is left out
  of the group sheets. Their valid answers still count in `Likert Items`.
  A participant with no Likert answers has an empty row and is not reported.
- **Groups.** Every labelled group is always listed, in code order; with
  N = 0 its statistics are empty. An `Unanswered` row appears only if someone
  in `Data` has an empty or -99 value in that column. An unexpected code gets
  its own row (e.g. `Degree code 9`) and is reported in `Validation`.
- **Statistics.** Sample stdev (n-1); one value gives an empty stdev. Six
  identical scores give a stdev of 0.
- **Duplicates.** A duplicate `ResponseId` keeps both rows, as in `Data`.

## Usage

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .

python -m experiment_transform "Trial Project_September 28 2026_18.35.xlsx" \
    -o resolution_calibration.xlsx
```

Only the raw export is needed. The answer key is stored in the code
(`src/experiment_transform/questions.py`).

## Where things are

```
src/experiment_transform/
├── config.py       # all coding rules and settings
├── questions.py    # the 9 questions: column codes + correct answers
├── transform.py    # loading, layout checks, coding, Excel output
├── resolution_calibration.py    # per-person calibration and gamma
├── performance_measures.py    # correct/incorrect and known/unknown sheets
├── likert.py       # Likert settings and calculations
├── likert_output.py # writes the Likert sheets
└── cli.py          # command-line entry point
tests/
├── test_resolution_calibration.py
├── test_performance_measures.py
├── test_transform.py
└── test_likert.py
```

Before coding anything, the program checks that every expected column
exists and that each question's 7 columns (4 timing, answer, confidence,
familiarity) are consecutive. If not, it stops with a list of problems.

## Development

```bash
python -m unittest discover -s tests -v
ruff check . && ruff format --check .
```

Code follows PEP 8 (line length 79, Google-style docstrings).

## Data privacy

`.gitignore` excludes `*.xlsx`, `*.sav` and `*.csv`, so participant data
is never committed.

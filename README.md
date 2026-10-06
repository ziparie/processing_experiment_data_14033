# processing_experiment_data_14033

Turns the raw Qualtrics export of the experiment into analysis-ready
files. The first output is a long-format table for computing
**resolution** and **calibration**.

## What it produces

One Excel workbook with three sheets:

| Sheet | Content |
|---|---|
| `Data` | One row per respondent per question (9 rows per respondent) |
| `Summary` | Counts, skipped respondents, coding settings used |
| `Validation` | Every value that could not be coded or looks suspicious |

### `Data` columns

| Column | Meaning | Coding |
|---|---|---|
| `UserId` | Qualtrics `ResponseId` (column H) | copied |
| `Question` | Question number 1–9 in presentation order | — |
| `Timing` | Seconds on the question page | `Page Submit` timing (see `config.TIMING_MEASURE`) |
| `Score` | Accuracy | 100 = correct, 0 = wrong, empty = unanswered (-99) |
| `Confidence` | Confidence rating 0–100 | copied; empty = unanswered (-99) |
| `Familiar` | "I know this question" | 2 or -99 → 0; 3 or empty → 1 |

Respondents with `Q1 = 2` (no consent) are skipped and listed in
`Summary`.

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
└── cli.py          # command-line entry point
tests/
└── test_transform.py
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

"""Add the Likert sheets to the workbook made by ``write_excel``."""

from pathlib import Path

import pandas as pd

from experiment_transform.likert import (
    ITEMS_SHEET,
    SCORES_SHEET,
    LikertResult,
)


def append_likert_sheets(likert: LikertResult, path: Path) -> None:
    """Append the six Likert sheets after the existing ones in a workbook."""
    sheets = {
        SCORES_SHEET: likert.scores,
        ITEMS_SHEET: likert.items,
        **likert.groups,
    }
    with pd.ExcelWriter(path, engine="openpyxl", mode="a") as writer:
        for name, table in sheets.items():
            table.to_excel(writer, sheet_name=name, index=False)

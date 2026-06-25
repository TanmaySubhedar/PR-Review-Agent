from typing import Literal

from pydantic import BaseModel


class ChangedSymbol(BaseModel):
    file: str
    symbol_name: str
    symbol_type: Literal["function", "class", "method", "import", "variable"]
    change_type: Literal["added", "modified", "deleted"]
    start_line: int
    end_line: int


class DiffPosition(BaseModel):
    """One row per line GitHub will accept an inline review comment on.

    `position` is the 1-indexed offset of the line within the file's unified
    diff patch text (per file), not the file's own line number - this is what
    GitHub's Review API requires for anchoring inline comments.
    """

    file: str
    new_line: int | None
    old_line: int | None
    position: int
    hunk_header: str


class DiffAnalysis(BaseModel):
    review_run_id: str
    changed_symbols: list[ChangedSymbol]
    risk_level: Literal["low", "medium", "high"]
    risk_score: int = 0
    risk_factors: list[str] = []
    diff_positions: list[DiffPosition] = []

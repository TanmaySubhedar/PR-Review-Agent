from typing import Literal

from pydantic import BaseModel


class ContextFileSelection(BaseModel):
    file: str
    selection_reason: Literal[
        "changed_file",
        "direct_caller",
        "direct_callee",
        "dependency_chain",
        "test_coverage",
        "same_module",
        "historical_relevance",
    ]
    score: float


class ReaderOutput(BaseModel):
    file: str
    purpose: str
    relevance: str
    risks: list[str] = []


class ContextPackage(BaseModel):
    selections: list[ContextFileSelection] = []
    reader_outputs: list[ReaderOutput] = []

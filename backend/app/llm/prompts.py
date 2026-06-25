from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def load_prompt(filename: str) -> str:
    """Loads a system prompt from the repo-root prompts/ directory, so the
    prompt text lives as a reviewable file rather than a Python string
    literal buried in pipeline code."""
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()

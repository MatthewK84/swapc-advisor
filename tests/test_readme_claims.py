"""Guard: every countable claim in the README must match the shipped code.

Exists because two README numbers once drifted from the data. A claim that
does not survive a grep is the most damaging defect a provenance-focused
repo can carry, so the counts are now asserted in CI.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swapc_advisor.retriever import EXPANSIONS

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
EQUIPMENT = json.loads(
    (ROOT / "src" / "swapc_advisor" / "data" / "equipment.json").read_text(encoding="utf-8")
)["equipment"]


def _claimed(pattern: str) -> int:
    match = re.search(pattern, README)
    assert match is not None, f"README claim not found: {pattern}"
    return int(match.group(1))


def test_readme_system_count_matches_data() -> None:
    assert _claimed(r"(\d+) systems, deliberately weighted low") == len(EQUIPMENT)


def test_readme_baseline_count_matches_data() -> None:
    actual = sum(1 for e in EQUIPMENT if e["baseline_comparator"])
    assert _claimed(r"(\d+) systems are flagged `baseline_comparator`") == actual


def test_readme_lexicon_count_matches_code() -> None:
    assert _claimed(r"(\d+)-entry domain lexicon") == len(EXPANSIONS)


def _count_test_functions() -> int:
    """Static count of test_* functions across the suite, no subprocess."""
    total: int = 0
    for path in (ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        )
    return total


def test_readme_test_count_matches_suite() -> None:
    assert _claimed(r"pytest\s+# (\d+) passed") == _count_test_functions()

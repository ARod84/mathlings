"""The quality-report numbers in the README say which code they came from."""

import re

from app.config import BACKEND_DIR
from app.puzzles.levels import GENERATOR_VERSION, LEVELS
from app.taxonomy.constants import TAXONOMY_COMMIT


def report_section() -> str:
    readme = (BACKEND_DIR / "README.md").read_text(encoding="utf-8")
    start = readme.index("### Quality report")
    return readme[start : readme.index("### Puzzle API", start)]


def test_readme_report_names_the_current_generator_version_and_taxonomy_commit():
    section = report_section()

    # If either of these changes, the numbers are from other code: rerun
    # `uv run python -m app.puzzles.report --all --count 5000` and update the table.
    assert f"**Generator version:** `{GENERATOR_VERSION}`" in section
    assert f"**Taxonomy commit:** `{TAXONOMY_COMMIT}`" in section
    assert re.search(r"\*\*Run on:\*\* \d{4}-\d{2}-\d{2}", section)


def test_readme_report_has_a_row_for_every_level():
    rows = re.findall(r"^\| (\d) +\| (\d+) of (\d+) \(", report_section(), flags=re.MULTILINE)

    assert [int(level) for level, _passed, _total in rows] == sorted(LEVELS)
    for _level, passed, total in rows:
        assert int(total) == 5000
        assert 0 <= int(passed) <= int(total)

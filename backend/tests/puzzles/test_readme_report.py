"""The quality-report numbers in the README say which code they came from."""

import re

from app.config import BACKEND_DIR
from app.puzzles.levels import FORM_WEIGHTS, GENERATOR_VERSION, LEVELS
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


def test_readme_report_compares_both_versions_for_every_level():
    section = report_section()
    assert "| Version 1 " in section
    assert "| Version 2 " in section

    # The coverage rows: "| ... | <level> | a of b (x%) | c of d (y%) |"
    start = section.index("Steps with at least one linked distractor")
    rows = re.findall(
        r"\| (\d) +\| \d+ of \d+ \((\d+\.\d)%\) \| \d+ of \d+ \((\d+\.\d)%\) \|",
        section[start : section.index("Steps where a linked rule applied")],
    )
    assert [int(level) for level, _before, _after in rows] == sorted(LEVELS)
    for _level, before, after in rows:
        assert float(after) > float(before)


def test_readme_records_the_form_weights():
    section = report_section()
    row = next(line for line in section.splitlines() if line.strip().startswith("| Weight"))
    recorded = [float(cell) for cell in row.strip().strip("|").split("|")[1:]]

    assert recorded == list(FORM_WEIGHTS.values())
    header = next(line for line in section.splitlines() if line.strip().startswith("| Form"))
    assert [cell.strip().strip("`") for cell in header.strip().strip("|").split("|")[1:]] == list(
        FORM_WEIGHTS
    )

import re

import pytest
from sqlmodel import Session

from app.config import get_settings
from app.db import make_engine
from app.puzzles.types.missing_number.diagnoser import diagnose
from app.puzzles.types.missing_number.equations import ALL_FORMS, render
from app.puzzles.types.missing_number.hints import build_hints
from app.puzzles.types.missing_number.levels import LEVELS
from app.puzzles.types.missing_number.misconceptions import (
    RULE_PATTERNS,
    MisconceptionResolutionError,
    resolve_catalog,
)
from app.puzzles.types.missing_number.models import MistakeRule
from app.puzzles.types.missing_number.report import build_report, format_catalog, format_puzzle
from app.puzzles.types.missing_number.taxonomy_link import (
    first_step_back,
    load_catalog,
    topic_exists,
)
from app.puzzles.types.missing_number.verified import generate_verified
from app.puzzles.types.missing_number.verifier import verify
from app.taxonomy.service import TaxonomyService, reload_graph
from tests.puzzles.support import (
    ERROR_PATTERN_ROWS,
    example_chain,
    make_catalog,
    make_puzzle,
    make_step,
)
from tests.puzzles.support import topic_exists as fake_topic_exists

# ---- the rule -> error pattern catalog ----


def test_catalog_resolves_each_mapped_rule():
    catalog = make_catalog()

    add_level_1 = catalog.link_for(MistakeRule.ADD_VISIBLE, "mt_3JgrHY221M")
    add_level_3 = catalog.link_for(MistakeRule.ADD_VISIBLE, "mt_XuHmIn2xje")
    assert add_level_1.error_pattern_id == "mt_3JgrHY221M#0"
    assert add_level_1.reteach_topic_id == "mt_oIzycTBeE4"
    assert add_level_1.pattern.startswith("Adds the two visible numbers")
    assert add_level_3.error_pattern_id == "mt_XuHmIn2xje#0"
    assert add_level_3.reteach_topic_id is None
    assert catalog.get("mt_XuHmIn2xje#0") is add_level_3
    assert catalog.get("mt_nope#9") is None


def test_catalog_prefers_the_primary_topic_then_falls_back():
    catalog = make_catalog()

    # Only one pattern exists for each of these, whatever the level.
    for primary in ("mt_3JgrHY221M", "mt_XuHmIn2xje", "mt_other"):
        assert (
            catalog.link_for(MistakeRule.ANSWER_LEFT_BACKWARDS, primary).error_pattern_id
            == "mt_3JgrHY221M#1"
        )
        assert (
            catalog.link_for(MistakeRule.POSITION_CONFUSION, primary).error_pattern_id
            == "mt_XuHmIn2xje#2"
        )


def test_rules_without_a_taxonomy_pattern_stay_unlinked():
    catalog = make_catalog()
    unlinked = (
        MistakeRule.OFF_BY_ONE_OVER,
        MistakeRule.OFF_BY_ONE_UNDER,
        MistakeRule.PLACE_VALUE_SLIP,
        MistakeRule.NEAR_MISS,
    )

    for rule in unlinked:
        assert rule not in RULE_PATTERNS
        assert not catalog.is_linked(rule)
        assert catalog.link_for(rule, "mt_3JgrHY221M") is None
    assert {rule for rule, pattern in catalog.table() if pattern is None} == set(unlinked)
    assert len([row for row in catalog.table() if row[1] is not None]) == 4


def test_resolution_fails_loudly_when_a_pattern_is_missing():
    rows = {topic: list(patterns) for topic, patterns in ERROR_PATTERN_ROWS.items()}
    rows["mt_XuHmIn2xje"] = rows["mt_XuHmIn2xje"][:2]  # drop "Position confusion"

    with pytest.raises(MisconceptionResolutionError, match=r"POSITION_CONFUSION.*found 0"):
        resolve_catalog(lambda topic_id: rows[topic_id])


def test_resolution_fails_loudly_when_a_pattern_is_ambiguous():
    rows = {topic: list(patterns) for topic, patterns in ERROR_PATTERN_ROWS.items()}
    rows["mt_3JgrHY221M"] = [*rows["mt_3JgrHY221M"], rows["mt_3JgrHY221M"][0]]

    with pytest.raises(MisconceptionResolutionError, match=r"ADD_VISIBLE.*found 2"):
        resolve_catalog(lambda topic_id: rows[topic_id])


def test_resolution_asks_for_each_topic_once():
    asked = []

    def lookup(topic_id):
        asked.append(topic_id)
        return ERROR_PATTERN_ROWS[topic_id]

    resolve_catalog(lookup)
    assert sorted(asked) == ["mt_3JgrHY221M", "mt_XuHmIn2xje"]


# ---- hints ----


def test_hints_for_the_spec_example():
    assert build_hints("a+?=c", 8, 11, 3) == [
        "The = sign means both sides are worth the same.",
        "What number do you add to 8 to make 11? Try 11 − 8.",
        "11 − 8 = 3, so the missing number is 3. Check: 8 + 3 = 11.",
    ]


def test_hints_for_an_answer_left_form():
    assert build_hints("c=?-b", 5, 3, 8) == [
        "The = sign means both sides are worth the same. The answer does not have to come last.",
        "5 is what is left when you take 3 from a number. Put them back together: try 5 + 3.",
        "5 + 3 = 8, so the missing number is 8. Check: 8 − 3 = 5.",
    ]


EXAMPLES = {
    "a+?=c": (8, 11),
    "?+b=c": (5, 12),
    "a-?=c": (14, 6),
    "?-b=c": (3, 5),
    "c=a+?": (11, 8),
    "c=?-b": (5, 3),
}


@pytest.mark.parametrize("form", ALL_FORMS)
def test_hint_tiers_for_every_form(form):
    first, second = EXAMPLES[form]
    step = make_step(form, first, second)
    meaning, strategy, worked = step.hints

    def numbers(text: str) -> list[int]:
        return [int(n) for n in re.findall(r"\d+", text)]

    # Tier 1 has no numbers at all, tier 2 only the visible ones, tier 3 the answer.
    assert numbers(meaning) == []
    assert set(numbers(strategy)) == {first, second}
    assert step.answer not in numbers(strategy)
    assert step.answer in numbers(worked)
    assert "Check:" in worked
    assert "Try" in strategy or "try" in strategy
    # Short enough for a child to read in one go.
    assert all(len(hint) <= 120 for hint in step.hints)
    # The worked step's check is the original equation with the box filled in.
    filled = render(step.equation, box=str(step.answer))
    left, right = filled.split(" = ")
    check = worked.split("Check: ")[1].rstrip(".")
    assert check in (f"{left} = {right}", f"{right} = {left}")


# ---- report helpers ----


def test_report_counts_add_up():
    report = build_report(2, 40, make_catalog(), fake_topic_exists)

    assert report.produced == 40
    assert report.failed == 0
    assert report.first_try + (report.produced - report.first_try) == 40
    assert report.steps == 100  # lengths 1, 2, 3, 4 in turn
    assert sum(report.forms.values()) == report.steps
    assert sum(report.rules.values()) == report.distractors == 300
    text = report.format()
    for wanted in ("passed on the first try", "average retries", "distractor rules", "slowest"):
        assert wanted in text


# Levels 1 and 2 are measured on the same 5000 seeds as the README report,
# because their margin over the target is thin (about 71-72% against 70%) and
# a small sample swings by more than that. Level 3 has room to spare, and its
# puzzles are slower to verify, so a smaller sample is enough there.
@pytest.mark.parametrize(
    ("level", "count", "target"), [(1, 5000, 0.70), (2, 5000, 0.70), (3, 600, 0.60)]
)
def test_enough_steps_carry_a_linked_distractor(level, count, target):
    """The signal the diagnoser gets: a wrong pick can only be explained if a
    linked option was there. Version 1 managed about 45%."""
    report = build_report(level, count, make_catalog(), fake_topic_exists)

    assert report.first_try == report.produced == count
    assert report.steps_with_linked / report.steps >= target
    # Nothing a linked rule produces is thrown away for being too large.
    assert report.steps_with_dropped == 0
    assert sum(report.linked_dropped.values()) == 0
    assert report.steps_with_linked == report.linked_distractors
    text = report.format()
    assert "steps with at least one linked distractor" in text
    assert "out of range" in text
    assert "best of 3" in text


def test_report_formatting_of_a_puzzle_and_the_catalog():
    text = format_puzzle(example_chain())
    assert "8 + □ = 11" in text
    assert "□ − 3 = 5" in text
    assert "ADD_VISIBLE  -> mt_3JgrHY221M#0" in text

    table = format_catalog(make_catalog())
    assert "POSITION_CONFUSION     mt_XuHmIn2xje#2" in table
    assert "PLACE_VALUE_SLIP       (none)" in table


# ---- against the real imported database ----


@pytest.mark.slow
def test_mapping_resolves_against_the_real_database():
    settings = get_settings()
    if not settings.database_path.is_file():
        pytest.skip("no database; run the migration and the importer first")
    engine = make_engine()
    with Session(engine) as session:
        service = TaxonomyService(session, reload_graph(session))
        if "mt_3JgrHY221M" not in service.graph:
            pytest.skip("the real taxonomy is not imported")

        catalog = load_catalog(service)
        exists = topic_exists(service)
        lookup = first_step_back(service)

        resolved = {
            (rule, pattern.error_pattern_id, pattern.reteach_topic_id)
            for rule, pattern in catalog.table()
            if pattern is not None
        }
        assert resolved == {
            (MistakeRule.ADD_VISIBLE, "mt_3JgrHY221M#0", "mt_oIzycTBeE4"),
            (MistakeRule.ADD_VISIBLE, "mt_XuHmIn2xje#0", None),
            (MistakeRule.ANSWER_LEFT_BACKWARDS, "mt_3JgrHY221M#1", "mt_oIzycTBeE4"),
            (MistakeRule.POSITION_CONFUSION, "mt_XuHmIn2xje#2", "mt_yTWxkzzoOZ"),
        }
        # The stand-in rows used by the other tests say what the real rows say.
        for topic_id, rows in ERROR_PATTERN_ROWS.items():
            real = {row.position: row for row in service.get_error_patterns(topic_id)}
            for row in rows:
                assert real[row.position].pattern.startswith(row.pattern[:30])
                real_reteach = real[row.position].reteach_prerequisite
                assert (real_reteach.id if real_reteach else None) == (
                    row.reteach_prerequisite.id if row.reteach_prerequisite else None
                )

        for spec in LEVELS.values():
            for topic_id in (spec.primary_topic_id, *spec.extra_topic_ids):
                assert exists(topic_id)
            assert lookup(spec.primary_topic_id) is not None
        assert not exists("mt_nope")

        for level in LEVELS:
            for seed in range(50):
                puzzle = generate_verified(seed, level, 4, catalog=catalog, topic_exists=exists)
                assert verify(puzzle, catalog=catalog, topic_exists=exists).ok

        # A level-3 "add the visible numbers" answer has no reteach topic of its
        # own, so the real prerequisite graph supplies one.
        puzzle = make_puzzle([make_step("a+?=c", 245, 380, level=3)], level=3)
        diagnosis = diagnose(puzzle, 0, 625, catalog=catalog, step_back=lookup)
        assert diagnosis.error_pattern_id == "mt_XuHmIn2xje#0"
        assert diagnosis.reteach_topic_id == lookup("mt_XuHmIn2xje")
        assert exists(diagnosis.reteach_topic_id)
    engine.dispose()

"""The adaptive engine: per-step topics, BKT, the recommendation policy and the simulator."""

import importlib.util
import itertools
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.adaptive.bkt import (
    Observation,
    mastery_from,
    posterior,
    prior_mastery,
    to_observation,
    update,
)
from app.adaptive.constants import (
    DEFAULT_BKT,
    FOCUS_WINDOW,
    MAX_OBSERVATIONS_PER_TOPIC,
    MIN_OBSERVATIONS_AFTER_LEVEL_CHANGE,
    MIN_OBSERVATIONS_FOR_LEVEL_CHANGE,
    PROMOTE_P_KNOWN,
    PROMOTE_RECENT_CORRECT,
    PROMOTE_RECENT_WINDOW,
    STEP_DOWN_P_KNOWN,
    BktParams,
)
from app.adaptive.policies import is_focused
from app.adaptive.policy import (
    consolidate_length,
    find_focus_rule,
    focus_for_next_puzzle,
    level_topic_ids,
    primary_topic_id,
    recommend_from,
)
from app.adaptive.service import AdaptiveService
from app.adaptive.simulate import KINDS, run_simulation
from app.config import BACKEND_DIR
from app.models import Attempt, Player
from app.puzzles.types.missing_number import MissingNumberChains
from app.puzzles.types.missing_number.equations import ALL_FORMS
from app.puzzles.types.missing_number.ids import make_puzzle_id
from app.puzzles.types.missing_number.levels import (
    ANSWER_LEFT_FORMS,
    LEVELS,
    TOPIC_EQUALS_SIGN,
    TOPIC_INVERSE,
    TOPIC_MISSING_NUMBER,
    TOPIC_UNKNOWN_ADD_SUB,
    step_topic_ids,
    topic_ids_for,
)
from app.taxonomy.importer import run_import
from tests.conftest import FIXTURE_COMMIT, PUZZLE_FIXTURE_TAXONOMY, migrate
from tests.puzzles.support import KNOWN_TOPICS, make_catalog
from tests.test_api import api_client, count_statements
from tests.test_players import attempts_of, check, hint
from tests.test_puzzle_api import internal, new_puzzle


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    database_path = tmp_path_factory.mktemp("adaptive") / "adaptive.db"
    engine = migrate(database_path)
    run_import(engine, PUZZLE_FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


def obs(
    correct: bool,
    level: int = 1,
    rules: tuple[str, ...] = (),
    form: str = "a+?=c",
    focused: bool = False,
):
    return Observation(
        level=level,
        topic_ids=tuple(step_topic_ids(level, form)),
        correct=correct,
        matched_rules=rules,
        focused=focused,
    )


def right(count: int, level: int = 1) -> list[Observation]:
    return [obs(True, level) for _ in range(count)]


def wrong(count: int, level: int = 1) -> list[Observation]:
    return [obs(False, level) for _ in range(count)]


# ---- per-step topics ----


def test_step_topics_at_levels_1_and_2():
    for level in (1, 2):
        for form in ALL_FORMS:
            expected = [TOPIC_UNKNOWN_ADD_SUB]
            if form in ("c=a+?", "c=?-b"):
                expected.append(TOPIC_EQUALS_SIGN)
            assert step_topic_ids(level, form) == expected, (level, form)
    assert step_topic_ids(1, "?-b=c") == [TOPIC_UNKNOWN_ADD_SUB]
    assert step_topic_ids(1, "c=?-b") == [TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN]


def test_step_topics_at_level_3_are_the_same_on_every_step():
    for form in ALL_FORMS:
        assert step_topic_ids(3, form) == [TOPIC_MISSING_NUMBER, TOPIC_INVERSE]


def test_a_puzzles_topics_are_the_union_of_its_steps_topics(client: TestClient):
    for level in (1, 2, 3):
        for seed in range(40):
            puzzle = internal(
                client, new_puzzle(client, level=level, length=4, seed=seed)["puzzle_id"]
            )
            union = []
            for step in puzzle.steps:
                union += [t for t in step_topic_ids(level, step.form) if t not in union]
            assert sorted(union) == sorted(puzzle.topic_ids)
            assert puzzle.topic_ids[0] == union[0]
    # shared/game-topics.json lists, per level, the union over every form.
    for level, spec in LEVELS.items():
        every = topic_ids_for(spec, list(ALL_FORMS))
        assert sorted({t for form in ALL_FORMS for t in step_topic_ids(level, form)}) == sorted(
            every
        )


def find_form(client: TestClient, level: int, wanted: set[str]):
    """A puzzle and the index of a step with one of the wanted forms."""
    for seed in range(300):
        puzzle = internal(client, new_puzzle(client, level=level, length=4, seed=seed)["puzzle_id"])
        for index, step in enumerate(puzzle.steps):
            # Only useful if the puzzle as a whole has more topics than this step.
            if step.form in wanted:
                return puzzle, index
    raise AssertionError(f"no step with a form in {wanted} at level {level}")


def test_a_check_stores_the_steps_topics_not_the_puzzles(client: TestClient):
    player = uuid.uuid4()

    # An answer-left step practises both topics.
    puzzle, index = find_form(client, 1, set(ANSWER_LEFT_FORMS))
    check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer, player)
    assert attempts_of(client, player)[-1].topic_ids == [TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN]

    # A ?-b=c step in a puzzle that also has an answer-left step: only the primary topic.
    for seed in range(300):
        puzzle = internal(client, new_puzzle(client, level=1, length=4, seed=seed)["puzzle_id"])
        forms = [step.form for step in puzzle.steps]
        if "?-b=c" in forms and TOPIC_EQUALS_SIGN in puzzle.topic_ids:
            break
    else:
        raise AssertionError("no suitable puzzle")
    index = forms.index("?-b=c")
    check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer, player)
    stored = attempts_of(client, player)[-1]
    assert stored.details == {"form": "?-b=c"}
    assert stored.topic_ids == [TOPIC_UNKNOWN_ADD_SUB]
    assert stored.topic_ids != puzzle.topic_ids

    puzzle, index = find_form(client, 3, set(ALL_FORMS))
    check(client, puzzle.puzzle_id, index, puzzle.steps[index].answer, player)
    assert attempts_of(client, player)[-1].topic_ids == [TOPIC_MISSING_NUMBER, TOPIC_INVERSE]


def load_migration_0003():
    path = BACKEND_DIR / "alembic" / "versions" / "0003_attempt_step_topics.py"
    spec = importlib.util.spec_from_file_location("migration_0003", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migrations_frozen_mapping_matches_step_topic_ids():
    migration = load_migration_0003()

    assert set(migration.ALL_FORMS) == set(ALL_FORMS)
    for level in LEVELS:
        for form in ALL_FORMS:
            assert migration.step_topic_ids(level, form) == step_topic_ids(level, form)


def test_migration_0003_rewrites_old_rows_from_their_level_and_form(tmp_path: Path):
    database_path = tmp_path / "old.db"
    engine = migrate(database_path, "0002")
    player = uuid.uuid4().hex
    whole_puzzle = json.dumps([TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN])
    rows = [
        # (level, form, topic_ids as stored before, expected after)
        (1, "?-b=c", whole_puzzle, [TOPIC_UNKNOWN_ADD_SUB]),
        (1, "c=a+?", whole_puzzle, [TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN]),
        (2, "a+?=c", whole_puzzle, [TOPIC_UNKNOWN_ADD_SUB]),
        (
            2,
            "c=?-b",
            json.dumps([TOPIC_UNKNOWN_ADD_SUB]),
            [TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN],
        ),
        (
            3,
            "a-?=c",
            json.dumps([TOPIC_MISSING_NUMBER, TOPIC_INVERSE]),
            [TOPIC_MISSING_NUMBER, TOPIC_INVERSE],
        ),
    ]
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO player (id, created_at, last_seen_at) VALUES (:id, :now, :now)"),
            {"id": player, "now": "2026-11-13 10:00:00.000000"},
        )
        for level, form, before, _after in rows:
            connection.execute(
                text(
                    "INSERT INTO attempt (player_id, puzzle_id, generator_version, game, level, "
                    "step_index, form, answer, correct, matched_rules, error_pattern_ids, "
                    "topic_ids, attempt_on_step, hint_tier_before, created_at) VALUES "
                    "(:player, 'p', '2', 'missing-number', :level, 0, :form, 1, 1, '[]', '[]', "
                    ":topics, 1, 0, '2026-11-13 10:00:00.000000')"
                ),
                {"player": player, "level": level, "form": form, "topics": before},
            )
        # A row of some other game is left alone.
        connection.execute(
            text(
                "INSERT INTO attempt (player_id, puzzle_id, generator_version, game, level, "
                "step_index, form, answer, correct, matched_rules, error_pattern_ids, "
                "topic_ids, attempt_on_step, hint_tier_before, created_at) VALUES "
                "(:player, 'p', '1', 'another-game', 1, 0, '?-b=c', 1, 1, '[]', '[]', "
                ":topics, 1, 0, '2026-11-13 10:00:00.000000')"
            ),
            {"player": player, "topics": whole_puzzle},
        )
    engine.dispose()

    engine = migrate(database_path, "0003")

    with engine.connect() as connection:
        stored = connection.execute(
            text("SELECT game, level, form, topic_ids FROM attempt ORDER BY id")
        ).all()
    engine.dispose()
    assert [json.loads(row.topic_ids) for row in stored[:-1]] == [after for *_rest, after in rows]
    assert stored[-1].game == "another-game"
    assert json.loads(stored[-1].topic_ids) == [TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN]


# ---- BKT ----


def test_the_default_parameters_are_the_documented_priors():
    assert BktParams() == DEFAULT_BKT
    assert (DEFAULT_BKT.p_init, DEFAULT_BKT.p_learn, DEFAULT_BKT.p_slip, DEFAULT_BKT.p_guess) == (
        0.30,
        0.15,
        0.10,
        0.25,
    )
    source = (BACKEND_DIR / "app" / "adaptive" / "constants.py").read_text(encoding="utf-8")
    assert "PRIORS, NOT FITTED VALUES" in source


def test_one_correct_observation_by_hand():
    # Bayes:  0.30 * 0.90 = 0.27 (knew it)   0.70 * 0.25 = 0.175 (guessed)
    #         0.27 / (0.27 + 0.175) = 0.606742
    # Learn:  0.606742 + (1 - 0.606742) * 0.15 = 0.665730
    assert posterior(0.30, True, DEFAULT_BKT) == pytest.approx(0.27 / 0.445)
    assert update(0.30, True, DEFAULT_BKT) == pytest.approx(0.6657303, abs=1e-6)


def test_one_incorrect_observation_by_hand():
    # Bayes:  0.30 * 0.10 = 0.03 (slipped)   0.70 * 0.75 = 0.525 (did not know)
    #         0.03 / (0.03 + 0.525) = 0.054054
    # Learn:  0.054054 + (1 - 0.054054) * 0.15 = 0.195946
    assert posterior(0.30, False, DEFAULT_BKT) == pytest.approx(0.03 / 0.555)
    assert update(0.30, False, DEFAULT_BKT) == pytest.approx(0.1959459, abs=1e-6)


def test_repeated_correct_answers_raise_p_known_every_time():
    p_known = DEFAULT_BKT.p_init
    seen = [p_known]
    for _ in range(25):
        p_known = update(p_known, True, DEFAULT_BKT)
        seen.append(p_known)

    assert all(later > earlier for earlier, later in itertools.pairwise(seen))
    assert 0.99 < seen[-1] < 1.0

    falling = [0.95]
    for _ in range(3):
        falling.append(update(falling[-1], False, DEFAULT_BKT))
    assert all(later < earlier for earlier, later in itertools.pairwise(falling))


def test_only_the_first_try_at_a_step_is_evidence():
    facts = {"hint_tier_before": 0, "correct": True, "level": 1, "topic_ids": ["t"]}

    assert to_observation(attempt_on_step=1, **facts) == Observation(1, ("t",), True)
    assert to_observation(attempt_on_step=2, **facts) is None
    assert to_observation(attempt_on_step=5, **facts) is None


@pytest.mark.parametrize(
    ("hint_tier", "answered_right", "counts_as_right"),
    [
        (0, True, True),
        (1, True, True),  # the meaning reminder changes nothing
        (2, True, False),  # the strategy hint was seen first
        (3, True, False),  # the worked step was seen first
        (0, False, False),
        (1, False, False),
        (3, False, False),
    ],
)
def test_a_first_try_after_a_strategy_hint_counts_as_incorrect(
    hint_tier, answered_right, counts_as_right
):
    observation = to_observation(
        attempt_on_step=1,
        hint_tier_before=hint_tier,
        correct=answered_right,
        level=2,
        topic_ids=["t"],
        matched_rules=["ADD_VISIBLE"],
    )

    assert observation.correct is counts_as_right
    assert observation.matched_rules == ("ADD_VISIBLE",)


def test_an_observation_counts_for_every_topic_of_its_step():
    both = obs(True, form="c=a+?")
    only_primary = obs(False, form="?-b=c")

    mastery = mastery_from([both, only_primary])

    assert mastery[(TOPIC_EQUALS_SIGN, 1)].observations == 1
    assert mastery[(TOPIC_EQUALS_SIGN, 1)].p_known == pytest.approx(update(0.3, True, DEFAULT_BKT))
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].observations == 2
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known == pytest.approx(
        update(update(0.3, True, DEFAULT_BKT), False, DEFAULT_BKT)
    )
    assert set(mastery) == {(TOPIC_UNKNOWN_ADD_SUB, 1), (TOPIC_EQUALS_SIGN, 1)}
    assert (
        mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].topic_id,
        mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].level,
    ) == (TOPIC_UNKNOWN_ADD_SUB, 1)


def test_each_level_keeps_its_own_estimate():
    """Levels 1 and 2 practise the same topic. Evidence from one never moves the other."""
    level_1, level_2 = right(8, level=1), wrong(6, level=2)

    mastery = mastery_from(level_1 + level_2)

    assert set(mastery) == {(TOPIC_UNKNOWN_ADD_SUB, 1), (TOPIC_UNKNOWN_ADD_SUB, 2)}
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)] == mastery_from(level_1)[(TOPIC_UNKNOWN_ADD_SUB, 1)]
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 2)] == mastery_from(level_2)[(TOPIC_UNKNOWN_ADD_SUB, 2)]
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known > 0.99
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 2)].p_known < 0.2
    # Interleaving the levels changes nothing either.
    mixed = [o for pair in zip(level_1, level_2, strict=False) for o in pair] + level_1[6:]
    assert mastery_from(mixed)[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known == pytest.approx(
        mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known
    )
    assert mastery_from(mixed)[(TOPIC_UNKNOWN_ADD_SUB, 2)].p_known == pytest.approx(
        mastery[(TOPIC_UNKNOWN_ADD_SUB, 2)].p_known
    )


def test_mastery_replays_only_the_latest_200_observations_per_topic_and_level():
    # 60 wrong answers that must be forgotten, then 200 that count.
    counted = [obs(index % 3 != 0) for index in range(MAX_OBSERVATIONS_PER_TOPIC)]
    history = wrong(60) + counted

    mastery = mastery_from(history)[(TOPIC_UNKNOWN_ADD_SUB, 1)]

    assert MAX_OBSERVATIONS_PER_TOPIC == 200
    assert mastery.observations == 200
    assert mastery.p_known == mastery_from(counted)[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known
    # The limit is per topic and level: a rarely practised one keeps its older observations.
    rare = obs(True, form="c=a+?")
    mixed = mastery_from([rare, *history])
    assert mixed[(TOPIC_EQUALS_SIGN, 1)].observations == 1
    assert mixed[(TOPIC_UNKNOWN_ADD_SUB, 1)].observations == 200
    other_level = mastery_from([*right(3, level=2), *history])
    assert other_level[(TOPIC_UNKNOWN_ADD_SUB, 2)].observations == 3
    assert other_level[(TOPIC_UNKNOWN_ADD_SUB, 1)].observations == 200


def test_mastery_keeps_the_time_of_the_last_observation():
    early, late = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 5, tzinfo=UTC)
    history = [
        Observation(1, (TOPIC_UNKNOWN_ADD_SUB,), True, at=early),
        Observation(1, (TOPIC_UNKNOWN_ADD_SUB,), True, at=late),
    ]

    assert mastery_from(history)[(TOPIC_UNKNOWN_ADD_SUB, 1)].last_practised == late
    assert prior_mastery("anything", 2).p_known == 0.30
    assert prior_mastery("anything", 2).observations == 0
    assert prior_mastery("anything", 2).level == 2


# ---- the policy ----


def test_cold_start():
    recommendation = recommend_from([])

    assert (recommendation.level, recommendation.length) == (1, 2)
    assert recommendation.reason_code == "cold_start"
    assert "No practice recorded yet" in recommendation.reason
    assert recommendation.focus_rule is None
    # The level 1 topics, at their prior.
    assert set(recommendation.mastery) == {(TOPIC_UNKNOWN_ADD_SUB, 1), (TOPIC_EQUALS_SIGN, 1)}
    assert all(m.p_known == 0.30 and m.observations == 0 for m in recommendation.mastery.values())


def test_promote():
    history = right(MIN_OBSERVATIONS_FOR_LEVEL_CHANGE)

    recommendation = recommend_from(history)

    assert recommendation.reason_code == "promote"
    assert (recommendation.level, recommendation.length) == (2, 2)
    assert "Move up to level 2" in recommendation.reason
    assert f"after {len(history)} first tries" in recommendation.reason
    assert "with 6 of the last 6 right" in recommendation.reason
    assert recommendation.mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known >= PROMOTE_P_KNOWN
    # The level 2 estimate starts from the prior: nothing carries over from level 1.
    assert recommendation.mastery[(TOPIC_UNKNOWN_ADD_SUB, 2)].observations == 0
    assert recommendation.mastery[(TOPIC_UNKNOWN_ADD_SUB, 2)].p_known == 0.30
    assert recommend_from(right(8, level=2)).level == 3
    # Level 3 topics appear at their prior, because that is what the child plays next.
    assert recommend_from(right(8, level=2)).mastery[(TOPIC_MISSING_NUMBER, 3)].observations == 0


def test_the_promotion_threshold_is_the_usual_bkt_mastery_level():
    assert PROMOTE_P_KNOWN == 0.95
    assert (PROMOTE_RECENT_CORRECT, PROMOTE_RECENT_WINDOW) == (5, 6)
    # Right, wrong, right, wrong... ending on two right: likely known, not yet mastered.
    history = [obs(index % 2 == 0) for index in range(7)] + right(1)
    p_known = mastery_from(history)[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known
    assert 0.85 <= p_known < PROMOTE_P_KNOWN

    assert recommend_from(history).reason_code == "consolidate"


def test_promotion_needs_five_of_the_last_six_first_tries_at_the_level_right():
    confident = right(10)
    four_of_six = [obs(answer) for answer in (False, True, False, True, True, True)]
    five_of_six = [obs(answer) for answer in (False, True, True, True, True, True)]
    # P(known) stays above the threshold in both cases: the estimate alone would promote.
    assert (
        mastery_from(confident + four_of_six)[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known >= PROMOTE_P_KNOWN
    )

    held = recommend_from(confident + four_of_six)
    assert (held.reason_code, held.level, held.length) == ("consolidate", 1, 4)
    assert recommend_from(confident + five_of_six).reason_code == "promote"

    # First tries at other levels are not part of the six.
    elsewhere = right(6, level=1) + [obs(False, level=2)] * 2 + right(4, level=2)
    assert mastery_from(elsewhere)[(TOPIC_UNKNOWN_ADD_SUB, 2)].observations == 6
    assert recommend_from(elsewhere).reason_code == "consolidate"


def test_promotion_needs_six_observations_at_the_current_level():
    history = right(MIN_OBSERVATIONS_FOR_LEVEL_CHANGE - 1)
    assert mastery_from(history)[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known >= PROMOTE_P_KNOWN

    recommendation = recommend_from(history)

    assert recommendation.reason_code == "consolidate"
    assert (recommendation.level, recommendation.length) == (1, 4)
    # Observations at another level do not count toward the six.
    assert recommend_from(right(8, level=1) + right(5, level=2)).reason_code == "consolidate"
    assert recommend_from(right(8, level=1) + right(6, level=2)).reason_code == "promote"


def test_step_down():
    history = wrong(MIN_OBSERVATIONS_FOR_LEVEL_CHANGE, level=2)
    assert mastery_from(history)[(TOPIC_UNKNOWN_ADD_SUB, 2)].p_known <= STEP_DOWN_P_KNOWN

    recommendation = recommend_from(history)

    assert recommendation.reason_code == "step_down"
    assert (recommendation.level, recommendation.length) == (1, 2)
    assert "Step back to level 1" in recommendation.reason
    # Level 3 steps down on its own primary topic.
    from_three = recommend_from(wrong(6, level=3))
    assert (from_three.reason_code, from_three.level, from_three.length) == ("step_down", 2, 2)


def test_step_down_needs_six_observations_at_the_current_level():
    recommendation = recommend_from(wrong(5, level=2))

    assert recommendation.reason_code == "consolidate"
    assert (recommendation.level, recommendation.length) == (2, 2)


def test_confidence_at_level_1_does_not_shield_a_learner_at_level_2():
    """With one shared estimate this took seven wrong answers in a row. Now it takes six,
    the minimum number of observations for any level change."""
    confident = right(8, level=1)

    five_wrong = recommend_from(confident + wrong(5, level=2))
    assert (five_wrong.reason_code, five_wrong.level) == ("consolidate", 2)

    six_wrong = recommend_from(confident + wrong(6, level=2))
    assert six_wrong.mastery[(TOPIC_UNKNOWN_ADD_SUB, 2)].p_known <= STEP_DOWN_P_KNOWN
    assert six_wrong.mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known > 0.99
    assert (six_wrong.reason_code, six_wrong.level) == ("step_down", 1)


@pytest.mark.parametrize(
    ("p_known", "length"),
    [(0.0, 2), (0.36, 2), (0.49, 2), (0.5, 3), (0.69, 3), (0.7, 4), (0.84, 4), (1.0, 4)],
)
def test_consolidate_length_grows_with_confidence(p_known, length):
    assert consolidate_length(p_known) == length


def test_consolidate():
    # Right, wrong, right, wrong... leaves p_known in the middle.
    history = [obs(index % 2 == 0) for index in range(9)]
    p_known = mastery_from(history)[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known
    assert STEP_DOWN_P_KNOWN < p_known < PROMOTE_P_KNOWN

    recommendation = recommend_from(history)

    assert recommendation.reason_code == "consolidate"
    assert recommendation.level == 1
    assert recommendation.length == consolidate_length(p_known)
    assert "Keep practising level 1" in recommendation.reason


def test_there_is_no_promotion_above_level_3_and_no_step_down_below_level_1():
    top = recommend_from(right(10, level=3))
    assert top.mastery[(TOPIC_MISSING_NUMBER, 3)].p_known >= PROMOTE_P_KNOWN
    assert (top.reason_code, top.level, top.length) == ("consolidate", 3, 4)

    bottom = recommend_from(wrong(10, level=1))
    assert bottom.mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known <= STEP_DOWN_P_KNOWN
    assert (bottom.reason_code, bottom.level, bottom.length) == ("consolidate", 1, 2)


def test_the_rules_are_tried_in_order():
    # cold_start comes first: nothing else can apply without observations.
    assert recommend_from([]).reason_code == "cold_start"
    # One observation is no longer a cold start, and too few for a level change.
    assert recommend_from(right(1)).reason_code == "consolidate"
    # The current level is the level of the latest observation.
    assert recommend_from(right(8, level=2) + right(1, level=1)).level == 1
    # promote and step_down cannot both hold: the thresholds do not overlap.
    assert STEP_DOWN_P_KNOWN < PROMOTE_P_KNOWN


def test_no_oscillation_after_a_step_down():
    """Up to level 2, down again, and then good answers at level 1.

    The level 1 estimate is untouched by level 2, so everything promotion asks
    for still holds at level 1. Without the guard the player would go straight
    back up; with it, four observations at the new level are needed first.
    """
    assert MIN_OBSERVATIONS_AFTER_LEVEL_CHANGE == 4
    # Six right at level 1 (promoted), then six wrong at level 2 (stepped down).
    before = right(6, level=1) + wrong(6, level=2)
    assert recommend_from(before).reason_code == "step_down"

    for new_observations in (1, 2, 3):
        history = before + right(new_observations, level=1)
        recommendation = recommend_from(history)
        assert recommendation.reason_code == "consolidate", new_observations
        assert recommendation.level == 1
        assert "it stays put until there are 4" in recommendation.reason
    # The guard, not the estimate, is what held it back.
    held = mastery_from(before + right(3, level=1))[(TOPIC_UNKNOWN_ADD_SUB, 1)]
    assert held.p_known >= PROMOTE_P_KNOWN
    assert held.observations >= MIN_OBSERVATIONS_FOR_LEVEL_CHANGE

    after_four = recommend_from(before + right(4, level=1))
    assert (after_four.reason_code, after_four.level) == ("promote", 2)


def test_no_oscillation_after_a_promotion():
    """Promoted to level 3 before, back at level 2 by choice, then wrong answers at level 3."""
    # Level 3 was visited (6 wrong: enough to step down), then level 2, then level 3 again.
    before = wrong(6, level=3) + right(6, level=2)
    assert recommend_from(before).reason_code == "promote"

    for new_observations in (1, 2, 3):
        recommendation = recommend_from(before + wrong(new_observations, level=3))
        assert recommendation.reason_code == "consolidate", new_observations
        assert recommendation.level == 3

    assert recommend_from(before + wrong(4, level=3)).reason_code == "step_down"


def test_a_first_level_needs_no_settling_in():
    # No level change has happened, so only the six-observation rule applies.
    assert recommend_from(right(6, level=2)).reason_code == "promote"


def test_focus_rule_needs_two_matches_in_the_last_eight_first_tries():
    assert FOCUS_WINDOW == 8
    once = [obs(False, rules=("ADD_VISIBLE",)), *right(3)]
    twice = [obs(False, rules=("ADD_VISIBLE",)), *right(3), obs(False, rules=("ADD_VISIBLE",))]

    assert recommend_from(once).focus_rule is None
    flagged = recommend_from(twice)
    assert flagged.focus_rule == "ADD_VISIBLE"
    assert "ADD_VISIBLE (2 of the last 5 first tries)" in flagged.reason

    # Slid out of the window: the first match is now nine first tries back.
    too_old = [obs(False, rules=("ADD_VISIBLE",)), *right(7), obs(False, rules=("ADD_VISIBLE",))]
    assert recommend_from(too_old).focus_rule is None
    assert find_focus_rule(too_old) is None


def test_focus_rule_picks_the_most_frequent_then_the_most_recent():
    history = [
        obs(False, rules=("OFF_BY_ONE_OVER",)),
        obs(False, rules=("ADD_VISIBLE", "POSITION_CONFUSION")),
        obs(False, rules=("ADD_VISIBLE",)),
        obs(False, rules=("OFF_BY_ONE_OVER",)),
        obs(False, rules=("ADD_VISIBLE",)),
    ]
    assert find_focus_rule(history) == ("ADD_VISIBLE", 3)

    tie = [
        obs(False, rules=("ADD_VISIBLE",)),
        obs(False, rules=("OFF_BY_ONE_OVER",)),
        obs(False, rules=("ADD_VISIBLE",)),
        obs(False, rules=("OFF_BY_ONE_OVER",)),
    ]
    assert find_focus_rule(tie) == ("OFF_BY_ONE_OVER", 2)
    assert find_focus_rule([]) is None


def test_focus_rule_does_not_change_the_level_or_length():
    plain = [obs(index % 2 == 0) for index in range(9)]
    with_rule = [
        obs(index % 2 == 0, rules=() if index % 2 == 0 else ("ADD_VISIBLE",)) for index in range(9)
    ]

    assert recommend_from(with_rule).focus_rule == "ADD_VISIBLE"
    assert (recommend_from(with_rule).level, recommend_from(with_rule).length) == (
        recommend_from(plain).level,
        recommend_from(plain).length,
    )


# ---- focus: which rule the next puzzle is generated with ----

ADD = ("ADD_VISIBLE",)


def test_focus_is_the_focus_rule_when_the_generator_can_target_it():
    for rule in ("ADD_VISIBLE", "ANSWER_LEFT_BACKWARDS", "POSITION_CONFUSION"):
        history = [obs(False, rules=(rule,)), obs(True), obs(False, rules=(rule,))]
        recommendation = recommend_from(history)
        assert (recommendation.focus_rule, recommendation.focus) == (rule, rule)
        assert "The next puzzle targets it." in recommendation.reason

    for rule in ("OFF_BY_ONE_OVER", "OFF_BY_ONE_UNDER", "PLACE_VALUE_SLIP"):
        history = [obs(False, rules=(rule,)), obs(False, rules=(rule,))]
        recommendation = recommend_from(history)
        assert (recommendation.focus_rule, recommendation.focus) == (rule, None)

    assert recommend_from([]).focus is None
    assert recommend_from(right(3)).focus is None
    assert focus_for_next_puzzle([], "ADD_VISIBLE") is None
    assert focus_for_next_puzzle(right(2), None) is None


def test_focus_is_null_right_after_a_focused_puzzle():
    mistakes = [obs(False, rules=ADD), obs(False, rules=ADD)]
    assert recommend_from(mistakes).focus == "ADD_VISIBLE"

    # The puzzle played last was focused: whatever happened in it, the next one is not.
    for last in (obs(True, focused=True), obs(False, rules=ADD, focused=True)):
        after_focused = recommend_from([*mistakes, last])
        assert after_focused.focus_rule == "ADD_VISIBLE"
        assert after_focused.focus is None
        assert "so the next one is an ordinary one" in after_focused.reason

    # One ordinary puzzle later it is offered again.
    after_plain = recommend_from([*mistakes, obs(True, focused=True), obs(True)])
    assert after_plain.focus == "ADD_VISIBLE"


def test_at_most_every_other_puzzle_in_a_round_is_focused():
    """Replay five puzzles of a player who makes the mistake on every first try.

    Each puzzle is as focused as the policy asked for. The pattern has to be
    focused, plain, focused, plain, focused: puzzles 1, 3 and 5 at most.
    """
    history = [obs(False, rules=ADD), obs(False, rules=ADD)]
    asked = []
    for _puzzle in range(5):
        focus = recommend_from(history).focus
        asked.append(focus)
        # Two steps per puzzle, both wrong in the same way.
        history += [obs(False, rules=ADD, focused=focus is not None)] * 2

    assert asked == ["ADD_VISIBLE", None, "ADD_VISIBLE", None, "ADD_VISIBLE"]
    assert all(not (a and b) for a, b in itertools.pairwise(asked))


def test_focus_is_released_when_the_rule_stops_matching():
    """Detection needs 2 matches in the last 8 first tries, so release needs no rule of its own."""
    mistakes = [obs(False, rules=ADD), obs(False, rules=ADD)]

    released_after = None
    for clean in range(0, 10):
        recommendation = recommend_from(mistakes + right(clean))
        if recommendation.focus_rule is None:
            assert recommendation.focus is None
            released_after = released_after or clean
        else:
            assert released_after is None
            assert recommendation.focus == "ADD_VISIBLE"

    # The second-to-last match slides out of the window of 8 after 7 clean first tries.
    assert released_after == FOCUS_WINDOW - 1 == 7
    # With 8 clean first tries the rule has not matched at all in the window.
    assert recommend_from(mistakes + right(8)).focus is None
    # One relapse is not enough to switch it back on; two are.
    assert recommend_from(mistakes + right(8) + [obs(False, rules=ADD)]).focus is None
    again = mistakes + right(8) + [obs(False, rules=ADD), obs(False, rules=ADD)]
    assert recommend_from(again).focus == "ADD_VISIBLE"


def test_focus_does_not_change_the_level_or_the_length():
    plain = [obs(index % 2 == 0) for index in range(9)]
    with_focus = [obs(i % 2 == 0, rules=() if i % 2 == 0 else ADD) for i in range(9)]

    a, b = recommend_from(plain), recommend_from(with_focus)
    assert b.focus == "ADD_VISIBLE"
    assert (a.level, a.length, a.reason_code) == (b.level, b.length, b.reason_code)


def test_a_focused_puzzle_is_recognised_by_its_id():
    assert is_focused(make_puzzle_id("3", 1, 3, 99, "av")) is True
    assert is_focused(make_puzzle_id("3", 1, 3, 99)) is False
    assert is_focused("mnc-2-1-2-16-eb38") is False  # an old id
    assert is_focused("hand-12") is False  # not an id at all


def test_primary_topics_and_level_topics():
    assert primary_topic_id(1) == primary_topic_id(2) == TOPIC_UNKNOWN_ADD_SUB
    assert primary_topic_id(3) == TOPIC_MISSING_NUMBER
    assert level_topic_ids(2) == [TOPIC_UNKNOWN_ADD_SUB, TOPIC_EQUALS_SIGN]
    assert level_topic_ids(3) == [TOPIC_MISSING_NUMBER, TOPIC_INVERSE]


# ---- the service, on stored attempts ----


def store_first_tries(
    client: TestClient,
    player: uuid.UUID,
    tries: list[tuple[int, bool]],
    *,
    start_minute: int = 0,
    rule: str = "ADD_VISIBLE",
) -> None:
    """Hand-built history: one first try per (level, correct), a minute apart.

    Each wrong one is stored as matching `rule`.
    """
    with Session(client.app.state.engine) as session:
        if session.get(Player, player) is None:
            session.add(
                Player(
                    id=player,
                    created_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
                    last_seen_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
                )
            )
            session.commit()
        for offset, (level, correct) in enumerate(tries):
            minute = start_minute + offset
            session.add(
                Attempt(
                    player_id=player,
                    puzzle_id=f"hand-{minute}",
                    generator_version="2",
                    game="missing-number",
                    level=level,
                    step_index=0,
                    form="a+?=c",
                    answer=5,
                    correct=correct,
                    matched_rules=[] if correct else [rule],
                    error_pattern_ids=[],
                    reteach_topic_id=None,
                    topic_ids=step_topic_ids(level, "a+?=c"),
                    attempt_on_step=1,
                    hint_tier_before=0,
                    created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=minute),
                )
            )
        session.commit()


def test_the_service_replays_stored_attempts_in_time_order(client: TestClient):
    player = uuid.uuid4()
    store_first_tries(client, player, [(1, True), (1, False), (1, True)])

    with Session(client.app.state.engine) as session:
        adaptive = AdaptiveService(session)
        observations = adaptive.observations(player)
        mastery = adaptive.mastery(player)

    assert [o.correct for o in observations] == [True, False, True]
    assert observations[1].matched_rules == ("ADD_VISIBLE",)
    expected = DEFAULT_BKT.p_init
    for correct in (True, False, True):
        expected = update(expected, correct, DEFAULT_BKT)
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].p_known == pytest.approx(expected)
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].observations == 3
    assert mastery[(TOPIC_UNKNOWN_ADD_SUB, 1)].last_practised is not None


def test_retries_and_hints_from_real_play_follow_the_evidence_rules(client: TestClient):
    player = uuid.uuid4()
    puzzle = internal(client, new_puzzle(client, level=1, length=4, seed=11)["puzzle_id"])
    puzzle_id = puzzle.puzzle_id
    steps = puzzle.steps

    # Step 0: wrong, then right. Only the first try counts: incorrect.
    check(client, puzzle_id, 0, steps[0].distractors[0].value, player)
    check(client, puzzle_id, 0, steps[0].answer, player)
    # Step 1: the tier 1 reminder, then right first time: correct.
    hint(client, puzzle_id, 1, 1, player)
    check(client, puzzle_id, 1, steps[1].answer, player)
    # Step 2: the strategy hint, then right first time: counts as incorrect.
    hint(client, puzzle_id, 2, 2, player)
    check(client, puzzle_id, 2, steps[2].answer, player)
    # Step 3: right first time, hint asked for afterwards: correct.
    check(client, puzzle_id, 3, steps[3].answer, player)
    hint(client, puzzle_id, 3, 3, player)

    with Session(client.app.state.engine) as session:
        observations = AdaptiveService(session).observations(player)

    assert [o.correct for o in observations] == [False, True, False, True]
    assert [list(o.topic_ids) for o in observations] == [
        step_topic_ids(1, step.form) for step in steps
    ]


def test_the_service_reads_at_most_200_observations_per_topic(client: TestClient):
    player = uuid.uuid4()
    # 30 old wrong answers, then 200 right ones: the old ones must not be read.
    store_first_tries(client, player, [(1, False)] * 30 + [(1, True)] * 200)

    with Session(client.app.state.engine) as session:
        observations = AdaptiveService(session).observations(player)

    assert len(observations) == 200
    assert all(o.correct for o in observations)

    # The limit is per topic and level: 5 first tries at level 2 are read as well.
    store_first_tries(client, player, [(2, True)] * 5, start_minute=300)
    with Session(client.app.state.engine) as session:
        assert len(AdaptiveService(session).observations(player)) == 205


def test_mastery_and_recommend_use_one_statement_whatever_the_history(client: TestClient):
    small, large, nobody = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    store_first_tries(client, small, [(1, True)])
    store_first_tries(client, large, [(1 + index % 3, index % 4 != 0) for index in range(450)])

    for player in (small, large, nobody):
        with Session(client.app.state.engine) as session:
            adaptive = AdaptiveService(session)
            with count_statements(client) as seen:
                adaptive.mastery(player)
            assert len(seen) == 1, seen
            with count_statements(client) as seen:
                adaptive.recommend(player, MissingNumberChains)
            assert len(seen) == 1, seen


def test_recommend_for_stored_players(client: TestClient):
    promoted, stepped_down, unknown = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    store_first_tries(client, promoted, [(1, True)] * 6)
    store_first_tries(client, stepped_down, [(2, False)] * 6)

    with Session(client.app.state.engine) as session:
        adaptive = AdaptiveService(session)
        up = adaptive.recommend(promoted, MissingNumberChains)
        down = adaptive.recommend(stepped_down, MissingNumberChains)
        cold = adaptive.recommend(unknown, MissingNumberChains)

    assert (up.reason_code, up.level, up.length) == ("promote", 2, 2)
    assert (down.reason_code, down.level, down.length) == ("step_down", 1, 2)
    assert down.focus_rule == "ADD_VISIBLE"
    assert (cold.reason_code, cold.level, cold.length) == ("cold_start", 1, 2)


def test_adaptive_modules_do_not_import_fastapi():
    folder = BACKEND_DIR / "app" / "adaptive"
    names = sorted(path.name for path in folder.glob("*.py"))
    assert {"bkt.py", "constants.py", "policy.py", "service.py", "simulate.py"} <= set(names)
    for name in names:
        source = (folder / name).read_text(encoding="utf-8")
        assert "fastapi" not in source, name
        assert "starlette" not in source, name
    # The model and the policy are plain Python: no database either.
    for name in ("bkt.py", "policy.py", "constants.py"):
        source = (folder / name).read_text(encoding="utf-8")
        assert "sqlalchemy" not in source and "sqlmodel" not in source, name


# ---- the simulator ----


def simulate(learners: int, steps: int, seed: int, focus: bool = True):
    return run_simulation(
        learners,
        steps,
        seed,
        catalog=make_catalog(),
        topic_exists=lambda topic_id: topic_id in KNOWN_TOPICS,
        focus=focus,
    )


def test_simulated_focus_is_capped_and_can_be_switched_off():
    on, off = simulate(24, 60, 5), simulate(24, 60, 5, focus=False)

    assert (on.focus, off.focus) == (True, False)
    assert on.mechanics.kind == off.mechanics.kind == "add_visible"
    # Focused puzzles happen, never two in a row, and never more than every other one.
    assert on.mechanics.focused_puzzles > 0
    assert on.mechanics.cap_holds and on.mechanics.back_to_back_focused == 0
    assert on.mechanics.focused_puzzles <= (on.mechanics.puzzles + 1) // 2
    assert 0 < on.mechanics.focused_while_flagged_percent <= 60
    # Switched off, the recommendation is ignored.
    assert off.mechanics.focused_puzzles == 0
    # The flag is released, and never long after the mistake stops: 7 first
    # tries for the window, plus up to 3 until the policy looks again.
    for mechanics in (on.mechanics, off.mechanics):
        assert mechanics.releases > 0
        assert mechanics.most_first_tries_to_release <= 10
    assert "no learning effect is measured" in on.format()
    assert simulate(24, 60, 5) == on


def test_the_simulator_says_plainly_that_it_measures_no_learning_effect():
    source = (BACKEND_DIR / "app" / "adaptive" / "simulate.py").read_text(encoding="utf-8")
    readme = (BACKEND_DIR / "README.md").read_text(encoding="utf-8")

    assert "reports NO learning effect of focus" in source
    assert "What this does not show: any learning effect." in readme
    assert "our own assumption shown back to us" in readme.replace("\n", " ")


def test_a_small_simulation_is_deterministic_and_reports_every_kind():
    first = simulate(16, 40, 7)
    second = simulate(16, 40, 7)

    assert first == second
    assert first.format() == second.format()
    assert [kind.kind for kind in first.kinds] == [kind.name for kind in KINDS]
    assert [kind.kind for kind in first.kinds] == ["fast", "slow", "strong", "add_visible"]
    assert all(kind.learners == 4 for kind in first.kinds)
    assert simulate(16, 40, 8) != first
    for line in ("false promo", "stuck at L1", "level changes", "focus flagged"):
        assert line in first.format()


def test_adding_learners_does_not_change_the_earlier_ones():
    small, larger = simulate(4, 30, 3), simulate(8, 30, 3)

    # One learner per kind in the small run; the larger run has those four first.
    assert small.kinds[2].learners == 1
    assert larger.kinds[2].learners == 2


@pytest.mark.slow
def test_the_full_simulation_is_deterministic_and_strong_learners_move_up():
    first = simulate(500, 120, 1)

    assert first == simulate(500, 120, 1)
    by_kind = {kind.kind: kind for kind in first.kinds}
    # Target: at most 5% of strong learners still at level 1 after 40 steps.
    assert first.strong_stuck_percent <= 5.0
    assert by_kind["strong"].reached_level_3_percent == 100.0
    assert by_kind["strong"].false_promotion_percent == 0.0
    # The persistent-misconception learners are flagged early.
    assert first.focus_flagged_percent >= 95.0


@pytest.mark.slow
@pytest.mark.xfail(
    strict=True,
    reason="Known limitation: about 40% of simulated learners are promoted at least once while "
    "their true skill is below 0.6 (target 5%). See 'Known limitation' in backend/README.md.",
)
def test_the_full_simulation_meets_the_false_promotion_target():
    assert simulate(500, 120, 1).false_promotion_percent <= 5.0

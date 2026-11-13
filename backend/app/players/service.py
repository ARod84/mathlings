"""Anonymous practice history. No FastAPI in here.

    players = PlayerService(session)
    players.record_attempt(player_id, AttemptRecord(...))   # one checked answer
    players.record_hint(player_id, puzzle_id, step_index, tier)
    players.summary(player_id)                              # per-topic numbers
    players.delete(player_id)                               # every row, for real

PRIVACY. A player is a random UUIDv4 that the browser made and keeps in its
localStorage. It is a pseudonymous identifier, NOT authentication: whoever
holds the id can read or delete its history. That is acceptable only because
the history is anonymous practice data (which steps, which answers, which
hints). Never store a name, email, birthday, age, IP address or user agent
next to it, never log it, and never treat it as proof of who is asking.

Every write commits on the session it was given, so it shares the request's
transaction with whatever that session did before.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, case, delete, func, insert, true
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, col, select

from app.models import Attempt, HintRequest, Player
from app.players.schemas import MistakeCount, PlayerSummary, PracticeTotals, TopicPractice

GAME_MISSING_NUMBER = "missing-number"
TOP_MISTAKES = 3


class PlayerNotFound(Exception):
    """No history is stored under this id."""


@dataclass(frozen=True)
class AttemptRecord:
    """One checked answer, as PuzzleService saw it."""

    puzzle_id: str
    generator_version: str
    game: str
    level: int
    step_index: int
    form: str
    answer: int
    correct: bool
    matched_rules: list[str]
    error_pattern_ids: list[str]
    reteach_topic_id: str | None
    topic_ids: list[str]


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _utc(moment: datetime) -> datetime:
    # SQLite hands datetimes back without a zone; they were stored in UTC.
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


class PlayerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- writing ----

    def record_attempt(self, player_id: uuid.UUID, record: AttemptRecord) -> None:
        """Store one checked answer. Three statements: player, the two counts, the row."""
        now = datetime.now(UTC)
        self._touch(player_id, now)
        same_step_attempts = and_(
            col(Attempt.player_id) == player_id,
            col(Attempt.puzzle_id) == record.puzzle_id,
            col(Attempt.step_index) == record.step_index,
        )
        same_step_hints = and_(
            col(HintRequest.player_id) == player_id,
            col(HintRequest.puzzle_id) == record.puzzle_id,
            col(HintRequest.step_index) == record.step_index,
        )
        # Both numbers describe the moment before this check, in one statement.
        earlier_attempts, highest_tier = self.session.execute(
            select(
                select(func.count())
                .select_from(Attempt)
                .where(same_step_attempts)
                .scalar_subquery(),
                select(func.coalesce(func.max(HintRequest.tier), 0))
                .where(same_step_hints)
                .scalar_subquery(),
            )
        ).one()
        self.session.execute(
            insert(Attempt).values(
                player_id=player_id,
                puzzle_id=record.puzzle_id,
                generator_version=record.generator_version,
                game=record.game,
                level=record.level,
                step_index=record.step_index,
                form=record.form,
                answer=record.answer,
                correct=record.correct,
                matched_rules=record.matched_rules,
                error_pattern_ids=record.error_pattern_ids,
                reteach_topic_id=record.reteach_topic_id,
                topic_ids=record.topic_ids,
                attempt_on_step=earlier_attempts + 1,
                hint_tier_before=highest_tier,
                created_at=now,
            )
        )
        self.session.commit()

    def record_hint(self, player_id: uuid.UUID, puzzle_id: str, step_index: int, tier: int) -> None:
        """Store one fetched hint tier. Two statements: player, the row."""
        now = datetime.now(UTC)
        self._touch(player_id, now)
        self.session.execute(
            insert(HintRequest).values(
                player_id=player_id,
                puzzle_id=puzzle_id,
                step_index=step_index,
                tier=tier,
                created_at=now,
            )
        )
        self.session.commit()

    def delete(self, player_id: uuid.UUID) -> None:
        """Delete the player and every row about them. Fine to call for an unknown id.

        The foreign keys cascade, but the child rows are deleted by name as
        well, so nothing depends on SQLite's foreign_keys pragma being on.
        """
        self.session.execute(delete(Attempt).where(col(Attempt.player_id) == player_id))
        self.session.execute(delete(HintRequest).where(col(HintRequest.player_id) == player_id))
        self.session.execute(delete(Player).where(col(Player.id) == player_id))
        self.session.commit()

    def _touch(self, player_id: uuid.UUID, now: datetime) -> None:
        """Create the player on first sight, otherwise move last_seen_at. One statement."""
        statement = sqlite_insert(Player).values(id=player_id, created_at=now, last_seen_at=now)
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["id"],
                set_={"last_seen_at": statement.excluded.last_seen_at},
            )
        )

    # ---- reading ----

    def summary(self, player_id: uuid.UUID) -> PlayerSummary:
        """Per-topic practice numbers. Five statements, whatever the history size.

        All counting happens in SQL. An attempt counts under every topic of its
        puzzle (attempt.topic_ids, unpacked with json_each). What comes back is
        one row per topic, or per topic and rule: bounded by the number of
        topics and rules, not by the number of attempts.
        """
        player = self.session.exec(select(Player).where(col(Player.id) == player_id)).first()
        if player is None:
            raise PlayerNotFound

        first_try = col(Attempt.attempt_on_step) == 1
        steps = func.coalesce(func.sum(case((first_try, 1), else_=0)), 0)
        first_try_correct = func.coalesce(
            func.sum(case((and_(first_try, col(Attempt.correct)), 1), else_=0)), 0
        )
        mine = col(Attempt.player_id) == player_id

        topic = func.json_each(col(Attempt.topic_ids)).table_valued("value").alias("topic")
        topic_rows = self.session.execute(
            select(
                topic.c.value,
                func.count(),
                steps,
                first_try_correct,
                func.max(col(Attempt.created_at)),
            )
            .select_from(Attempt)
            .join(topic, true())
            .where(mine)
            .group_by(topic.c.value)
        ).all()

        rule = func.json_each(col(Attempt.matched_rules)).table_valued("value").alias("rule")
        mistake_rows = self.session.execute(
            select(topic.c.value, rule.c.value, func.count())
            .select_from(Attempt)
            .join(topic, true())
            .join(rule, true())
            .where(mine)
            .group_by(topic.c.value, rule.c.value)
        ).all()

        # A hint belongs to the topics of the step it was fetched for, which
        # the step's first attempt knows. Hints for a step that was never
        # checked count in the totals only.
        hint_rows = self.session.execute(
            select(topic.c.value, func.count())
            .select_from(HintRequest)
            .join(
                Attempt,
                and_(
                    col(Attempt.player_id) == col(HintRequest.player_id),
                    col(Attempt.puzzle_id) == col(HintRequest.puzzle_id),
                    col(Attempt.step_index) == col(HintRequest.step_index),
                    first_try,
                ),
            )
            .join(topic, true())
            .where(col(HintRequest.player_id) == player_id)
            .group_by(topic.c.value)
        ).all()

        attempts, total_steps, total_first_correct, correct, hint_requests = self.session.execute(
            select(
                func.count(),
                steps,
                first_try_correct,
                func.coalesce(func.sum(case((col(Attempt.correct), 1), else_=0)), 0),
                select(func.count())
                .select_from(HintRequest)
                .where(col(HintRequest.player_id) == player_id)
                .scalar_subquery(),
            )
            .select_from(Attempt)
            .where(mine)
        ).one()

        hints_by_topic = {topic_id: count for topic_id, count in hint_rows}
        mistakes_by_topic: dict[str, list[MistakeCount]] = {}
        # Most frequent first; the rule name settles ties, so the order is stable.
        for topic_id, rule_name, count in sorted(mistake_rows, key=lambda r: (r[0], -r[2], r[1])):
            mistakes_by_topic.setdefault(topic_id, []).append(
                MistakeCount(rule=rule_name, count=count)
            )

        topics = [
            TopicPractice(
                topic_id=topic_id,
                attempts=topic_attempts,
                steps=topic_steps,
                first_try_correct_rate=_rate(first_correct, topic_steps),
                hints_per_step=_rate(hints_by_topic.get(topic_id, 0), topic_steps),
                top_mistakes=mistakes_by_topic.get(topic_id, [])[:TOP_MISTAKES],
                last_practised=_utc(last_practised),
            )
            for topic_id, topic_attempts, topic_steps, first_correct, last_practised in sorted(
                topic_rows, key=lambda r: (-r[1], r[0])
            )
        ]
        return PlayerSummary(
            player_since=_utc(player.created_at),
            totals=PracticeTotals(
                attempts=attempts,
                steps=total_steps,
                correct=correct,
                hint_requests=hint_requests,
                first_try_correct_rate=_rate(total_first_correct, total_steps),
                hints_per_step=_rate(hint_requests, total_steps),
            ),
            topics=topics,
        )

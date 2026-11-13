"""Mastery and recommendations for a stored player. No FastAPI in here.

    adaptive = AdaptiveService(session)
    adaptive.mastery(player_id)                  # {(topic_id, level): TopicMastery}
    adaptive.recommend(player_id, puzzle_type)   # Recommendation: level, parameters and why

Nothing is stored: mastery is replayed from the attempt history on every
call. That costs one query per call, whatever the size of the history,
because the query itself keeps only the latest observations per topic and level.
"""

import uuid

from sqlalchemy import func, true
from sqlmodel import Session, col, select

from app.adaptive.bkt import (
    MasteryKey,
    Observation,
    TopicMastery,
    mastery_from,
    to_observation,
)
from app.adaptive.constants import EVIDENCE_ATTEMPT_ON_STEP, MAX_OBSERVATIONS_PER_TOPIC
from app.adaptive.policies import POLICIES, no_policy
from app.adaptive.policy import Recommendation
from app.models import Attempt
from app.puzzles.core import PuzzleType
from app.puzzles.types.missing_number.levels import GAME as MISSING_NUMBER


class AdaptiveService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def observations(self, player_id: uuid.UUID, game: str = MISSING_NUMBER) -> list[Observation]:
        """The player's observations in one game, oldest first. One statement.

        Only first tries are read, and per topic and level only the latest
        MAX_OBSERVATIONS_PER_TOPIC of them (row_number over the topics that
        json_each unpacks), so the result has a fixed upper size. The game's
        policy says which puzzles were focused; without a policy, none are.
        """
        policy = POLICIES.get(game)
        first_tries = (
            col(Attempt.player_id) == player_id,
            col(Attempt.game) == game,
            col(Attempt.attempt_on_step) == EVIDENCE_ATTEMPT_ON_STEP,
        )
        topic = func.json_each(col(Attempt.topic_ids)).table_valued("value").alias("topic")
        ranked = (
            select(
                col(Attempt.id).label("attempt_id"),
                func.row_number()
                .over(
                    partition_by=(topic.c.value, col(Attempt.level)),
                    order_by=(col(Attempt.created_at).desc(), col(Attempt.id).desc()),
                )
                .label("recency"),
            )
            .select_from(Attempt)
            .join(topic, true())
            .where(*first_tries)
            .subquery()
        )
        rows = self.session.execute(
            select(
                col(Attempt.attempt_on_step),
                col(Attempt.hint_tier_before),
                col(Attempt.correct),
                col(Attempt.level),
                col(Attempt.topic_ids),
                col(Attempt.matched_rules),
                col(Attempt.created_at),
                col(Attempt.puzzle_id),
            )
            .where(
                col(Attempt.id).in_(
                    select(ranked.c.attempt_id).where(
                        ranked.c.recency <= MAX_OBSERVATIONS_PER_TOPIC
                    )
                )
            )
            .order_by(col(Attempt.created_at), col(Attempt.id))
        ).all()

        observations = []
        for row in rows:
            attempt_on_step, hint_tier, correct, level, topic_ids, rules, created_at = row[:7]
            observation = to_observation(
                attempt_on_step=attempt_on_step,
                hint_tier_before=hint_tier,
                correct=correct,
                level=level,
                topic_ids=topic_ids,
                matched_rules=rules,
                at=created_at,
                focused=policy.is_focused(row.puzzle_id) if policy else False,
            )
            if observation is not None:
                observations.append(observation)
        return observations

    def mastery(self, player_id: uuid.UUID) -> dict[MasteryKey, TopicMastery]:
        """P(known) per (topic id, level) the player has practised.

        From Missing Number Chains only, as before. No other game stores
        attempts yet, and two games that share a topic would need a decision
        about how their levels compare before their evidence could be mixed.
        """
        return mastery_from(self.observations(player_id))

    def recommend(self, player_id: uuid.UUID, puzzle_type: type[PuzzleType]) -> Recommendation:
        """What to play next in a game.

        With a policy for the game: its answer for this player's observations
        (a player with no attempts, or unknown, gets its cold start). Without
        one: the game's default, and the history is not read at all.
        """
        policy = POLICIES.get(puzzle_type.game)
        if policy is None:
            return no_policy(puzzle_type)
        return policy.recommend(self.observations(player_id, puzzle_type.game))

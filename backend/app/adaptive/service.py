"""Mastery and recommendations for a stored player. No FastAPI in here.

    adaptive = AdaptiveService(session)
    adaptive.mastery(player_id)     # {(topic_id, level): TopicMastery}
    adaptive.recommend(player_id)   # Recommendation: level, length and why

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
from app.adaptive.policy import Recommendation, recommend_from
from app.models import Attempt
from app.players.service import GAME_MISSING_NUMBER


class AdaptiveService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def observations(self, player_id: uuid.UUID) -> list[Observation]:
        """The player's observations, oldest first. One statement.

        Only first tries are read, and per topic and level only the latest
        MAX_OBSERVATIONS_PER_TOPIC of them (row_number over the topics that
        json_each unpacks), so the result has a fixed upper size.
        """
        first_tries = (
            col(Attempt.player_id) == player_id,
            col(Attempt.game) == GAME_MISSING_NUMBER,
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
            attempt_on_step, hint_tier, correct, level, topic_ids, rules, created_at = row
            observation = to_observation(
                attempt_on_step=attempt_on_step,
                hint_tier_before=hint_tier,
                correct=correct,
                level=level,
                topic_ids=topic_ids,
                matched_rules=rules,
                at=created_at,
            )
            if observation is not None:
                observations.append(observation)
        return observations

    def mastery(self, player_id: uuid.UUID) -> dict[MasteryKey, TopicMastery]:
        """P(known) per (topic id, level) the player has practised."""
        return mastery_from(self.observations(player_id))

    def recommend(self, player_id: uuid.UUID) -> Recommendation:
        """What to play next. A player with no attempts (or unknown) gets the cold start."""
        return recommend_from(self.observations(player_id))

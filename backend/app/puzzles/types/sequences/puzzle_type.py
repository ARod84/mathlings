""" "Next in Line" as a PuzzleType.

Nothing is decided here. Each method hands over to the module that does the
work (generator, verifier, diagnoser, public, levels), with the catalog and
the two taxonomy lookups this instance was loaded with.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Self

from app.puzzles.core import (
    CheckOutcome,
    LevelInfo,
    NewPuzzleBody,
    PuzzleKey,
    PuzzleType,
    PuzzleTypeUnavailable,
)
from app.puzzles.core.catalog import MisconceptionResolutionError
from app.puzzles.core.taxonomy_link import first_step_back, topic_exists
from app.puzzles.types.sequences import generator
from app.puzzles.types.sequences.diagnoser import diagnose
from app.puzzles.types.sequences.ids import TYPE_CODE, decode_fields
from app.puzzles.types.sequences.levels import (
    GAME,
    GENERATOR_VERSION,
    LEVELS,
    MAX_ANSWER,
    MIN_ANSWER,
    level_topic_ids,
    step_topic_ids,
)
from app.puzzles.types.sequences.misconceptions import SequenceCatalog, resolve_catalog
from app.puzzles.types.sequences.models import SequencePuzzle
from app.puzzles.types.sequences.public import to_public
from app.puzzles.types.sequences.schemas import NewSequenceRequest, SequencePublic
from app.puzzles.types.sequences.verifier import VerificationResult, verify
from app.taxonomy.service import TaxonomyService, TopicNotFound


@dataclass(frozen=True)
class SequenceParams:
    """Nothing yet: the level and the seed decide the whole puzzle."""


class NumberSequences(PuzzleType[SequencePuzzle, SequenceParams]):
    type_code = TYPE_CODE
    game = GAME
    generator_version = GENERATOR_VERSION
    levels = MappingProxyType(
        {level: LevelInfo(level, tuple(level_topic_ids(level))) for level in LEVELS}
    )
    request_model = NewSequenceRequest
    public_model = SequencePublic
    answer_min = MIN_ANSWER
    answer_max = MAX_ANSWER

    def __init__(
        self,
        catalog: SequenceCatalog,
        *,
        topic_exists: Callable[[str], bool],
        step_back: Callable[[str], str | None],
    ) -> None:
        self.catalog = catalog
        self._topic_exists = topic_exists
        self._step_back = step_back

    @classmethod
    def load(cls, taxonomy: TaxonomyService) -> Self:
        try:
            catalog = resolve_catalog(taxonomy.get_error_patterns)
        except (MisconceptionResolutionError, TopicNotFound) as error:
            raise PuzzleTypeUnavailable(f"the rule mapping did not resolve: {error}") from error
        return cls(
            catalog, topic_exists=topic_exists(taxonomy), step_back=first_step_back(taxonomy)
        )

    # ---- parameters and ids ----

    @classmethod
    def default_params(cls) -> SequenceParams:
        return SequenceParams()

    @classmethod
    def params_from_request(cls, request: NewPuzzleBody) -> SequenceParams:
        return SequenceParams()

    @classmethod
    def params_to_request(cls, params: SequenceParams) -> dict[str, Any]:
        return {}

    @classmethod
    def decode_key(cls, fields: Sequence[str]) -> PuzzleKey[SequenceParams]:
        level, seed = decode_fields(fields)
        return PuzzleKey(level, seed, SequenceParams())

    # ---- the pipeline ----

    def generate(self, seed: int, level: int, params: SequenceParams) -> SequencePuzzle:
        return generator.generate(seed, level, self.catalog)

    def verify(self, puzzle: SequencePuzzle) -> VerificationResult:
        return verify(puzzle, catalog=self.catalog, topic_exists=self._topic_exists)

    def to_public(self, puzzle: SequencePuzzle) -> SequencePublic:
        return to_public(puzzle)

    def check(self, puzzle: SequencePuzzle, step: int, answer: int) -> CheckOutcome:
        diagnosis = diagnose(puzzle, step, answer, catalog=self.catalog, step_back=self._step_back)
        primary_topic_id = LEVELS[puzzle.level].topic_ids[puzzle.kind][0]
        links = (self.catalog.link_for(rule, primary_topic_id) for rule in diagnosis.matched_rules)
        return CheckOutcome(
            correct=diagnosis.correct,
            matched_rules=tuple(rule.value for rule in diagnosis.matched_rules),
            # In the order of matched_rules; a rule without a taxonomy pattern adds nothing.
            error_pattern_ids=tuple(
                dict.fromkeys(link.error_pattern_id for link in links if link is not None)
            ),
            reteach_topic_id=diagnosis.reteach_topic_id,
        )

    def hint_tiers(self, puzzle: SequencePuzzle, step: int) -> int:
        return len(puzzle.steps[step].hints)

    def hint(self, puzzle: SequencePuzzle, step: int, tier: int) -> str:
        """From 1 (where to look) to 3 (worked step, which shows the answer)."""
        return puzzle.steps[step].hints[tier - 1]

    # ---- what is stored with an attempt ----

    def step_topic_ids(self, puzzle: SequencePuzzle, step: int) -> list[str]:
        return step_topic_ids(puzzle.level, puzzle.kind)

    def attempt_details(self, puzzle: SequencePuzzle, step: int) -> dict[str, Any]:
        return {
            "kind": puzzle.kind,
            "position": puzzle.steps[step].position,
            "terms": len(puzzle.terms),
        }

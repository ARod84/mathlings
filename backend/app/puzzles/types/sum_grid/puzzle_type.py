"""Sum Grid as a PuzzleType.

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
from app.puzzles.types.sum_grid import generator
from app.puzzles.types.sum_grid.diagnoser import diagnose
from app.puzzles.types.sum_grid.ids import TYPE_CODE, decode_fields
from app.puzzles.types.sum_grid.levels import (
    GAME,
    GENERATOR_VERSION,
    LEVELS,
    MAX_ANSWER,
    MIN_ANSWER,
    step_topic_ids,
)
from app.puzzles.types.sum_grid.misconceptions import SumGridCatalog, resolve_catalog
from app.puzzles.types.sum_grid.models import SumGridPuzzle
from app.puzzles.types.sum_grid.public import to_public
from app.puzzles.types.sum_grid.schemas import NewSumGridRequest, SumGridPublic
from app.puzzles.types.sum_grid.verifier import VerificationResult, verify
from app.taxonomy.service import TaxonomyService, TopicNotFound


@dataclass(frozen=True)
class SumGridParams:
    """Nothing yet: the level and the seed decide the whole puzzle."""


class SumGrid(PuzzleType[SumGridPuzzle, SumGridParams]):
    type_code = TYPE_CODE
    game = GAME
    generator_version = GENERATOR_VERSION
    levels = MappingProxyType(
        {level: LevelInfo(level, spec.topic_ids) for level, spec in LEVELS.items()}
    )
    request_model = NewSumGridRequest
    public_model = SumGridPublic
    answer_min = MIN_ANSWER
    answer_max = MAX_ANSWER

    def __init__(
        self,
        catalog: SumGridCatalog,
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
    def default_params(cls) -> SumGridParams:
        return SumGridParams()

    @classmethod
    def params_from_request(cls, request: NewPuzzleBody) -> SumGridParams:
        return SumGridParams()

    @classmethod
    def params_to_request(cls, params: SumGridParams) -> dict[str, Any]:
        return {}

    @classmethod
    def decode_key(cls, fields: Sequence[str]) -> PuzzleKey[SumGridParams]:
        level, seed = decode_fields(fields)
        return PuzzleKey(level, seed, SumGridParams())

    # ---- the pipeline ----

    def generate(self, seed: int, level: int, params: SumGridParams) -> SumGridPuzzle:
        return generator.generate(seed, level, self.catalog)

    def verify(self, puzzle: SumGridPuzzle) -> VerificationResult:
        return verify(puzzle, catalog=self.catalog, topic_exists=self._topic_exists)

    def to_public(self, puzzle: SumGridPuzzle) -> SumGridPublic:
        return to_public(puzzle)

    def check(self, puzzle: SumGridPuzzle, step: int, answer: int) -> CheckOutcome:
        diagnosis = diagnose(puzzle, step, answer, catalog=self.catalog, step_back=self._step_back)
        primary_topic_id = LEVELS[puzzle.level].topic_ids[0]
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

    def hint_tiers(self, puzzle: SumGridPuzzle, step: int) -> int:
        return len(puzzle.steps[step].hints)

    def hint(self, puzzle: SumGridPuzzle, step: int, tier: int) -> str:
        """From 1 (where to look) to 3 (worked step, which shows the answer)."""
        return puzzle.steps[step].hints[tier - 1]

    # ---- what is stored with an attempt ----

    def step_topic_ids(self, puzzle: SumGridPuzzle, step: int) -> list[str]:
        return step_topic_ids(puzzle.level)

    def attempt_details(self, puzzle: SumGridPuzzle, step: int) -> dict[str, Any]:
        this = puzzle.steps[step]
        return {
            "size": puzzle.size,
            "cell": [this.cell.row, this.cell.col],
            "line": this.line.kind,
            "line_index": this.line.index,
        }

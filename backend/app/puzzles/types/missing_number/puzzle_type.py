"""Missing Number Chains as a PuzzleType: the first implementation of the contract.

Nothing is decided here. Each method hands over to the module that has always
done the work (generator, verifier, diagnoser, public, levels), with the
catalog and the two taxonomy lookups this instance was loaded with.
"""

import logging
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
from app.puzzles.core.ids import InvalidPuzzleId
from app.puzzles.types.missing_number import generator
from app.puzzles.types.missing_number.diagnoser import diagnose
from app.puzzles.types.missing_number.equations import ALL_FORMS
from app.puzzles.types.missing_number.ids import TYPE_CODE, decode_fields
from app.puzzles.types.missing_number.levels import (
    DEFAULT_LENGTH,
    FOCUS_BY_CODE,
    GAME,
    GENERATOR_VERSION,
    LEVELS,
    step_topic_ids,
    supported_focus,
    topic_ids_for,
)
from app.puzzles.types.missing_number.misconceptions import (
    MisconceptionCatalog,
    MisconceptionResolutionError,
)
from app.puzzles.types.missing_number.models import MistakeRule, Puzzle
from app.puzzles.types.missing_number.public import to_public
from app.puzzles.types.missing_number.schemas import NewPuzzleRequest, PuzzlePublic
from app.puzzles.types.missing_number.taxonomy_link import (
    first_step_back,
    load_catalog,
    topic_exists,
)
from app.puzzles.types.missing_number.verifier import VerificationResult, verify
from app.taxonomy.service import TaxonomyService, TopicNotFound

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MissingNumberParams:
    # Number of steps in the chain.
    length: int = DEFAULT_LENGTH
    # A mistake rule to target (levels.FOCUS_TARGET_FORMS), or None.
    focus: MistakeRule | None = None


class MissingNumberChains(PuzzleType[Puzzle, MissingNumberParams]):
    type_code = TYPE_CODE
    game = GAME
    generator_version = GENERATOR_VERSION
    levels = MappingProxyType(
        {
            level: LevelInfo(level, tuple(topic_ids_for(spec, list(ALL_FORMS))))
            for level, spec in LEVELS.items()
        }
    )
    request_model = NewPuzzleRequest
    public_model = PuzzlePublic

    def __init__(
        self,
        catalog: MisconceptionCatalog,
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
            catalog = load_catalog(taxonomy)
        except (MisconceptionResolutionError, TopicNotFound) as error:
            raise PuzzleTypeUnavailable(f"the rule mapping did not resolve: {error}") from error
        return cls(
            catalog, topic_exists=topic_exists(taxonomy), step_back=first_step_back(taxonomy)
        )

    # ---- parameters and ids ----

    @classmethod
    def default_params(cls) -> MissingNumberParams:
        return MissingNumberParams()

    @classmethod
    def params_from_request(cls, request: NewPuzzleBody) -> MissingNumberParams:
        assert isinstance(request, NewPuzzleRequest)
        return MissingNumberParams(length=request.length, focus=request.focus)

    @classmethod
    def params_to_request(cls, params: MissingNumberParams) -> dict[str, Any]:
        # The focus is sent only when there is one.
        fields: dict[str, Any] = {"length": params.length}
        if params.focus is not None:
            fields["focus"] = params.focus.value
        return fields

    @classmethod
    def decode_key(cls, fields: Sequence[str]) -> PuzzleKey[MissingNumberParams]:
        level, length, seed, focus_code = decode_fields(fields)
        focus = None
        if focus_code is not None:
            focus = FOCUS_BY_CODE.get(focus_code)
            if focus is None:
                raise InvalidPuzzleId(f"focus code {focus_code!r} is not one this generator knows")
        return PuzzleKey(level, seed, MissingNumberParams(length, focus))

    def normalize_params(self, params: MissingNumberParams) -> MissingNumberParams:
        if params.focus is not None and supported_focus(params.focus) is None:
            # Only some mistake rules can be targeted. The rest change nothing.
            logger.info(
                "Focus %s has no effect on generation; making a puzzle without it",
                params.focus.value,
            )
            return MissingNumberParams(params.length)
        return params

    # ---- the pipeline ----

    def generate(self, seed: int, level: int, params: MissingNumberParams) -> Puzzle:
        # Called with four arguments when there is no focus, exactly as before.
        if params.focus is None:
            return generator.generate(seed, level, params.length, self.catalog)
        return generator.generate(seed, level, params.length, self.catalog, params.focus)

    def verify(self, puzzle: Puzzle) -> VerificationResult:
        return verify(puzzle, catalog=self.catalog, topic_exists=self._topic_exists)

    def to_public(self, puzzle: Puzzle) -> PuzzlePublic:
        return to_public(puzzle)

    def check(self, puzzle: Puzzle, step: int, answer: int) -> CheckOutcome:
        diagnosis = diagnose(puzzle, step, answer, catalog=self.catalog, step_back=self._step_back)
        primary_topic_id = LEVELS[puzzle.level].primary_topic_id
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

    def hint_tiers(self, puzzle: Puzzle, step: int) -> int:
        return len(puzzle.steps[step].hints)

    def hint(self, puzzle: Puzzle, step: int, tier: int) -> str:
        """From 1 (meaning) to 3 (worked step, which shows the answer)."""
        return puzzle.steps[step].hints[tier - 1]

    # ---- what is stored with an attempt ----

    def step_topic_ids(self, puzzle: Puzzle, step: int) -> list[str]:
        # The step's own topics, not the puzzle's: see levels.step_topic_ids.
        return step_topic_ids(puzzle.level, puzzle.steps[step].form)

    def attempt_details(self, puzzle: Puzzle, step: int) -> dict[str, Any]:
        return {"form": puzzle.steps[step].form}

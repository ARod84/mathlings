"""A second puzzle type, as small as one can be. It exists only in the tests.

"Type the number shown": one step, which shows a number, and the answer is
that number. One known mistake: typing the number one higher (ONE_MORE).

tests/test_puzzle_contract.py registers it next to the real types and plays
it through the generic routes. Nothing in it imports the missing-number
chain, so whatever works here works because of app/puzzles/core, the
registry and the shared service, and not because of anything chains do.
"""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from app.puzzles.core import (
    CheckOutcome,
    GenerationError,
    LevelInfo,
    NewPuzzleBody,
    PublicPuzzle,
    PuzzleKey,
    PuzzleType,
    PuzzleTypeUnavailable,
)
from app.puzzles.core.ids import InvalidPuzzleId, make_id, seed_field
from app.taxonomy.service import TaxonomyService

# A topic of the puzzle fixture taxonomy. Any real topic would do.
DUMMY_TOPIC = "mt_3JgrHY221M"
ONE_MORE = "ONE_MORE"
MAX_DIGITS = 3


@dataclass(frozen=True)
class DummyParams:
    # How many digits the number shown has.
    digits: int = 1


class DummyStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    shown: int


class DummyPuzzle(BaseModel):
    """The server-side puzzle. Satisfies core.InternalPuzzle."""

    model_config = ConfigDict(frozen=True)

    puzzle_id: str
    generator_version: str
    seed: int
    level: int
    digits: int
    steps: list[DummyStep]


class DummyNewPuzzle(NewPuzzleBody):
    level: int = Field(ge=1, le=1)
    digits: int = Field(default=1, ge=1, le=MAX_DIGITS)


class DummyPublic(PublicPuzzle):
    game: Literal["dummy"] = "dummy"
    shown: int
    hint_tiers: int = 1


@dataclass(frozen=True)
class DummyVerification:
    names: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.names


def dummy_id(version: str, level: int, digits: int, seed: int) -> str:
    return make_id(DummyType.type_code, version, [str(level), str(digits), seed_field(seed)])


class DummyType(PuzzleType[DummyPuzzle, DummyParams]):
    type_code = "dum"
    game = "dummy"
    # Version 2, so that an id from version 1 is "older" and must give a 410.
    generator_version = "2"
    levels = MappingProxyType({1: LevelInfo(1, (DUMMY_TOPIC,))})
    request_model = DummyNewPuzzle
    public_model = DummyPublic
    # The topic the type cannot work without. A subclass can name one that is not there.
    required_topic = DUMMY_TOPIC

    def __init__(self, topic_exists: Callable[[str], bool]) -> None:
        self._topic_exists = topic_exists

    @classmethod
    def load(cls, taxonomy: TaxonomyService) -> Self:
        graph = taxonomy.graph
        if cls.required_topic not in graph:
            raise PuzzleTypeUnavailable(f"topic {cls.required_topic} is not in the taxonomy")
        return cls(lambda topic_id: topic_id in graph)

    # ---- parameters and ids ----

    @classmethod
    def default_params(cls) -> DummyParams:
        return DummyParams()

    @classmethod
    def params_from_request(cls, request: NewPuzzleBody) -> DummyParams:
        assert isinstance(request, DummyNewPuzzle)
        return DummyParams(digits=request.digits)

    @classmethod
    def params_to_request(cls, params: DummyParams) -> dict[str, Any]:
        return {"digits": params.digits}

    @classmethod
    def decode_key(cls, fields: Sequence[str]) -> PuzzleKey[DummyParams]:
        try:
            level, digits, seed = fields
            return PuzzleKey(int(level), int(seed, 36), DummyParams(int(digits)))
        except ValueError as error:
            raise InvalidPuzzleId(f"not the fields of a dummy id: {fields}") from error

    # ---- the pipeline ----

    def generate(self, seed: int, level: int, params: DummyParams) -> DummyPuzzle:
        if level not in self.levels:
            raise ValueError(f"unknown level {level}")
        if not 1 <= params.digits <= MAX_DIGITS:
            raise ValueError(f"digits must be between 1 and {MAX_DIGITS}")
        shown = random.Random(seed).randint(10 ** (params.digits - 1), 10**params.digits - 1)
        if shown % 10 == 9:
            # One more than a number ending in 9 has other digits, which a real
            # type might not want to offer. Here it is just a reason to retry.
            raise GenerationError(f"seed {seed} shows {shown}, which ends in 9")
        return DummyPuzzle(
            puzzle_id=dummy_id(self.generator_version, level, params.digits, seed),
            generator_version=self.generator_version,
            seed=seed,
            level=level,
            digits=params.digits,
            steps=[DummyStep(shown=shown)],
        )

    def verify(self, puzzle: DummyPuzzle) -> DummyVerification:
        names = []
        if len(puzzle.steps) != 1:
            names.append("not_one_step")
        elif len(str(puzzle.steps[0].shown)) != puzzle.digits:
            names.append("wrong_number_of_digits")
        if puzzle.puzzle_id != dummy_id(
            puzzle.generator_version, puzzle.level, puzzle.digits, puzzle.seed
        ):
            names.append("puzzle_id_mismatch")
        if not self._topic_exists(DUMMY_TOPIC):
            names.append("unknown_topic")
        return DummyVerification(names)

    def to_public(self, puzzle: DummyPuzzle) -> DummyPublic:
        return DummyPublic(
            puzzle_id=puzzle.puzzle_id, level=puzzle.level, shown=puzzle.steps[0].shown
        )

    def check(self, puzzle: DummyPuzzle, step: int, answer: int) -> CheckOutcome:
        shown = puzzle.steps[step].shown
        if answer == shown:
            return CheckOutcome(correct=True)
        if answer == shown + 1:
            return CheckOutcome(correct=False, matched_rules=(ONE_MORE,))
        return CheckOutcome(correct=False)

    def hint_tiers(self, puzzle: DummyPuzzle, step: int) -> int:
        return 1

    def hint(self, puzzle: DummyPuzzle, step: int, tier: int) -> str:
        return f"Type the number you can see: {puzzle.steps[step].shown}."

    # ---- what is stored with an attempt ----

    def step_topic_ids(self, puzzle: DummyPuzzle, step: int) -> list[str]:
        return [DUMMY_TOPIC]

    def attempt_details(self, puzzle: DummyPuzzle, step: int) -> dict[str, Any]:
        return {"shown": puzzle.steps[step].shown, "digits": puzzle.digits}


class UnloadableDummyPublic(DummyPublic):
    game: Literal["dummy-unloadable"] = "dummy-unloadable"


class UnloadableDummyType(DummyType):
    """The same game under another name, needing a topic no taxonomy has."""

    type_code = "dmx"
    game = "dummy-unloadable"
    public_model = UnloadableDummyPublic
    required_topic = "mt_not_a_topic"

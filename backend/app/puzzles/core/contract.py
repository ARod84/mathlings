"""The contract every puzzle type implements. Nothing here knows about any one game.

A puzzle type is a class. Its identity (type_code, game, generator_version,
levels, the request and public models) is on the class, so the registry can
answer "which game is this id for?" before any taxonomy is loaded. An
instance is the type bound to the taxonomy it needs: `load` builds one, and
PuzzleRuntime (service.py) keeps it until the taxonomy changes.

The pipeline every type goes through, all of it in shared code:

    generate -> verify -> to_public        core/verified.py, service.py
    check, hint                            service.py
    attempt_details, step_topic_ids        service.py, when an attempt is stored

To add a type, see "How to add a puzzle type" in backend/README.md.
"""

from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field

from app.puzzles.core.ids import MAX_SEED
from app.taxonomy.service import TaxonomyService


class GenerationError(Exception):
    """This seed cannot produce a valid puzzle. The caller should try another."""


class PuzzleTypeUnavailable(Exception):
    """The type cannot be served with the taxonomy as it is (a topic it needs is missing)."""


@dataclass(frozen=True)
class LevelInfo:
    level: int
    # Every topic a puzzle at this level can practise, primary first. The
    # same list as the game's entry in shared/game-topics.json.
    topic_ids: tuple[str, ...]


class InternalPuzzle(Protocol):
    """What shared code reads from a type's server-side puzzle. Never sent to a browser."""

    @property
    def puzzle_id(self) -> str: ...
    @property
    def generator_version(self) -> str: ...
    @property
    def seed(self) -> int: ...
    @property
    def level(self) -> int: ...
    @property
    def steps(self) -> Sequence[Any]: ...


class VerificationResult(Protocol):
    @property
    def ok(self) -> bool: ...

    # The name of each way the puzzle breaks its rules. Empty when ok.
    @property
    def names(self) -> Collection[str]: ...


@dataclass(frozen=True)
class CheckOutcome:
    """What a type says about one answer to one step."""

    correct: bool
    # Names of the known mistakes that give this answer; empty when the answer
    # is right, and when it is wrong in a way no rule explains.
    matched_rules: tuple[str, ...] = ()
    # "<topic id>#<position>" of each matched rule's taxonomy error pattern,
    # in the order of matched_rules. A rule without a pattern adds nothing.
    error_pattern_ids: tuple[str, ...] = ()
    # Where to step back to, if the mistake was recognized.
    reteach_topic_id: str | None = None

    @property
    def unrecognized(self) -> bool:
        """Wrong, and no known mistake explains it."""
        return not self.correct and not self.matched_rules


@dataclass(frozen=True)
class PuzzleKey[ParamsT]:
    """What a puzzle id decodes to, next to its type and generator version."""

    level: int
    seed: int
    params: ParamsT


class NewPuzzleBody(BaseModel):
    """What every "new puzzle" request carries. A type adds its own parameters."""

    model_config = ConfigDict(extra="forbid")

    level: int
    seed: int | None = Field(
        default=None,
        ge=0,
        le=MAX_SEED,
        description="Fixes the puzzle. Leave out for a random one.",
    )


class PublicPuzzle(BaseModel):
    """What every puzzle sent to a browser carries. A type adds its own shape.

    A type narrows `game` to a Literal of its own name. That is the field
    the API's responses are discriminated on.
    """

    game: str
    puzzle_id: str
    level: int


class PuzzleType[PuzzleT: InternalPuzzle, ParamsT](ABC):
    """One kind of puzzle: how it is made, verified, shown, checked and hinted."""

    # ---- identity ----

    # The prefix of this type's puzzle ids, for example "mnc".
    type_code: ClassVar[str]
    # The game's name in URLs, in attempt.game and in shared/game-topics.json.
    game: ClassVar[str]
    # Bumped whenever the same seed can give a different puzzle. Whole numbers
    # written as text, so an id from an older version can be told apart (410).
    generator_version: ClassVar[str]
    levels: ClassVar[Mapping[int, LevelInfo]]
    # The body of POST /puzzles/{game}, and what to_public returns.
    request_model: ClassVar[type[NewPuzzleBody]]
    public_model: ClassVar[type[PublicPuzzle]]

    @classmethod
    @abstractmethod
    def load(cls, taxonomy: TaxonomyService) -> Self:
        """The type, bound to the current taxonomy.

        Reads whatever it needs from the database now, because the instance
        outlives the request. Raises PuzzleTypeUnavailable if the taxonomy
        lacks something the type cannot work without.
        """

    # ---- parameters and ids ----

    @classmethod
    @abstractmethod
    def default_params(cls) -> ParamsT:
        """The parameters of a puzzle nobody asked anything particular of."""

    @classmethod
    @abstractmethod
    def params_from_request(cls, request: NewPuzzleBody) -> ParamsT:
        """The type's parameters out of a validated `request_model`."""

    @classmethod
    @abstractmethod
    def params_to_request(cls, params: ParamsT) -> dict[str, Any]:
        """The other way round: the request fields, besides level and seed, asking for `params`."""

    @classmethod
    @abstractmethod
    def decode_key(cls, fields: Sequence[str]) -> PuzzleKey[ParamsT]:
        """Level, seed and parameters from the middle fields of an id (core/ids.py).

        Raises InvalidPuzzleId if they are not ones this type writes.
        """

    def normalize_params(self, params: ParamsT) -> ParamsT:
        """`params` as the generator will act on them. Most types change nothing."""
        return params

    # ---- the pipeline ----

    @abstractmethod
    def generate(self, seed: int, level: int, params: ParamsT) -> PuzzleT:
        """One puzzle for exactly these inputs, the same every time.

        Raises GenerationError if this seed cannot work, and ValueError for
        inputs the type never accepts. Does not check its own work.
        """

    @abstractmethod
    def verify(self, puzzle: PuzzleT) -> VerificationResult:
        """Every way `puzzle` breaks the type's rules, found without trusting `generate`."""

    @abstractmethod
    def to_public(self, puzzle: PuzzleT) -> PublicPuzzle:
        """The child-facing view: no answers, rule names or hint text."""

    @abstractmethod
    def check(self, puzzle: PuzzleT, step: int, answer: int) -> CheckOutcome:
        """Is `answer` right for this step, and if not, which known mistake gives it."""

    @abstractmethod
    def hint_tiers(self, puzzle: PuzzleT, step: int) -> int:
        """How many hint tiers this step has. Tiers are numbered from 1."""

    @abstractmethod
    def hint(self, puzzle: PuzzleT, step: int, tier: int) -> str:
        """One hint tier, written for a child. `tier` is already known to exist."""

    # ---- what is stored with an attempt ----

    @abstractmethod
    def step_topic_ids(self, puzzle: PuzzleT, step: int) -> list[str]:
        """The topics this one step practises, primary first."""

    @abstractmethod
    def attempt_details(self, puzzle: PuzzleT, step: int) -> dict[str, Any]:
        """Type-specific facts about the step, kept in attempt.details. JSON values only."""

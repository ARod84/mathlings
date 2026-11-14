"""Puzzles of every type, for Python callers and for the HTTP layer. No FastAPI in here.

Nothing in this file knows about any one game. A game is looked up in the
registry and everything it does goes through the PuzzleType contract
(app/puzzles/core/contract.py).

Stateless: nothing about a puzzle is stored. A puzzle is rebuilt from its
puzzle_id on every call and verified again before it is used.

The one thing that can be stored is practice history, and only when the caller
passes a player id to `check` or `hint` (and the service was given a
PlayerService). Without one, nothing is written. See app/players/service.py.

    runtime = PuzzleRuntime(default_registry())    # one per process
    runtime.refresh(taxonomy_service)              # loads the types when needed
    service = PuzzleService(taxonomy_service, runtime)
    puzzle = service.new_puzzle("missing-number", level=1)
    result = service.check(puzzle.puzzle_id, 0, 19)
"""

import logging
import secrets
import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.players.service import AttemptRecord, PlayerService
from app.puzzles.core import (
    InternalPuzzle,
    NewPuzzleBody,
    PublicPuzzle,
    PuzzleType,
    PuzzleTypeUnavailable,
)
from app.puzzles.core.ids import (
    MAX_SEED,
    InvalidPuzzleId,
    OutdatedPuzzleId,
    RawPuzzleId,
    split_id,
)
from app.puzzles.core.schemas import CheckResult, DiagnosisPublic, HintOut, ReteachTopic
from app.puzzles.core.verified import PuzzleRejected, generate_verified, regenerate
from app.puzzles.registry import PuzzleRegistry
from app.taxonomy.service import TaxonomyService

logger = logging.getLogger(__name__)
# One line per checked answer. The start of the data an adaptive engine will need.
check_log = logging.getLogger("app.puzzles.checks")


class PuzzleError(Exception):
    """Base for the errors a caller is expected to handle."""


class PuzzleNotFound(PuzzleError):
    def __init__(self, puzzle_id: str) -> None:
        super().__init__(f"Puzzle not found: {puzzle_id}")
        self.puzzle_id = puzzle_id


class PuzzleVersionGone(PuzzleError):
    """The id is genuine, but from an older generator whose puzzles can no longer be rebuilt."""

    def __init__(self, puzzle_id: str, current_version: str) -> None:
        super().__init__(f"Puzzle {puzzle_id} is from an older generator version")
        self.puzzle_id = puzzle_id
        self.current_version = current_version


class StepNotFound(PuzzleError):
    def __init__(self, puzzle_id: str, step_index: int, steps: int) -> None:
        super().__init__(f"Puzzle {puzzle_id} has no step {step_index}")
        self.puzzle_id = puzzle_id
        self.step_index = step_index
        self.steps = steps


class HintTierNotFound(PuzzleError):
    def __init__(self, tier: int, tiers: int) -> None:
        super().__init__(f"There is no hint tier {tier}")
        self.tier = tier
        self.tiers = tiers


class AnswerOutOfBounds(PuzzleError):
    """The answer is not a number this game ever accepts. Nothing was checked."""

    def __init__(self, answer: int, minimum: int, maximum: int) -> None:
        super().__init__(f"An answer must be between {minimum} and {maximum}")
        self.answer = answer
        self.minimum = minimum
        self.maximum = maximum


class PuzzlesUnavailable(PuzzleError):
    """A puzzle type could not be loaded against the taxonomy as it is."""


class PuzzleRuntime:
    """The registered puzzle types, loaded and kept for the life of the process.

    Loading a type reads the database (a chain resolves its mistake-rule
    catalog), so it is done once and reused. `refresh` loads them again only
    when the prerequisite graph has been reloaded since (a re-import), which
    it can tell from the graph's version stamp.
    """

    def __init__(self, registry: PuzzleRegistry) -> None:
        self.registry = registry
        # By game. A type that could not be loaded is in `errors` instead.
        self.types: dict[str, PuzzleType] = {}
        self.errors: dict[str, str] = {}
        # How many times the types have been loaded. For tests and for curiosity.
        self.load_count = 0
        self._loaded = False
        self._graph_version: object = None

    def refresh(self, taxonomy: TaxonomyService) -> None:
        version = taxonomy.graph.version
        if self._loaded and version == self._graph_version:
            return
        self.load_count += 1
        self._loaded, self._graph_version = True, version
        self.types, self.errors = {}, {}
        for puzzle_type in self.registry:
            try:
                self.types[puzzle_type.game] = puzzle_type.load(taxonomy)
            except PuzzleTypeUnavailable as error:
                self.errors[puzzle_type.game] = str(error)
                logger.warning("%s puzzles are unavailable: %s", puzzle_type.game, error)

    def require(self, game: str) -> PuzzleType:
        """The loaded type for a registered game."""
        puzzle_type = self.types.get(game)
        if puzzle_type is None:
            raise PuzzlesUnavailable(
                "Puzzles are unavailable: the taxonomy does not have the topics they need."
            )
        return puzzle_type


class PuzzleService:
    def __init__(
        self,
        taxonomy: TaxonomyService,
        runtime: PuzzleRuntime,
        players: PlayerService | None = None,
    ) -> None:
        self.taxonomy = taxonomy
        self.runtime = runtime
        self.players = players

    def new_puzzle(
        self, game: str, level: int, params: Any = None, seed: int | None = None
    ) -> PublicPuzzle:
        """A new verified puzzle. Without a seed, one is drawn at random.

        `params` are the type's own parameters (for a chain, MissingNumberParams);
        without them the type's defaults are used. The public puzzle does not
        say what it was made with.

        Raises registry.UnknownGame for a game nobody registered, and
        core.verified.PuzzleGenerationFailed if every attempt fails.
        """
        puzzle_type = self.runtime.require(self.runtime.registry.by_game(game).game)
        if seed is None:
            seed = secrets.randbelow(MAX_SEED + 1)
        return puzzle_type.to_public(generate_verified(puzzle_type, seed, level, params))

    def new_puzzle_from(self, game: str, request: NewPuzzleBody) -> PublicPuzzle:
        """`new_puzzle` for a request body already validated as the game's request_model."""
        params = self.runtime.registry.by_game(game).params_from_request(request)
        return self.new_puzzle(game, request.level, params, request.seed)

    def get_puzzle(self, puzzle_id: str) -> PublicPuzzle:
        puzzle_type, puzzle = self._rebuild(puzzle_id)
        return puzzle_type.to_public(puzzle)

    def check(
        self,
        puzzle_id: str,
        step_index: int,
        answer: int,
        player_id: uuid.UUID | None = None,
        context: str | None = None,
    ) -> CheckResult:
        """Check one answer. Never reveals the right answer when the child is wrong.

        With a player id the attempt is stored; the result is the same either way.
        `context` says where the check comes from ("daily" for Today's Puzzle)
        and is kept in the stored attempt's details; ordinary play sends none,
        and then the details are exactly what the puzzle type gives.
        """
        started = time.perf_counter()
        puzzle_type, raw = self._type_of(puzzle_id)
        # The bounds are the type's own, so they are checked as soon as the id
        # says which type it is, and before any work is done for the answer.
        if not puzzle_type.answer_min <= answer <= puzzle_type.answer_max:
            raise AnswerOutOfBounds(answer, puzzle_type.answer_min, puzzle_type.answer_max)
        puzzle = self._regenerate(puzzle_type, raw, puzzle_id)
        self._require_step(puzzle, step_index)
        outcome = puzzle_type.check(puzzle, step_index, answer)

        reteach = None
        if outcome.reteach_topic_id is not None:
            summaries = self.taxonomy.get_summaries([outcome.reteach_topic_id])
            summary = summaries.get(outcome.reteach_topic_id)
            if summary is not None:
                reteach = ReteachTopic(id=summary.id, name=summary.name)

        is_last = step_index == len(puzzle.steps) - 1
        result = CheckResult(
            correct=outcome.correct,
            feedback="correct" if outcome.correct else "try_again",
            diagnosis=DiagnosisPublic(
                matched_rules=list(outcome.matched_rules),
                unrecognized=outcome.unrecognized,
                reteach_topic=reteach,
            ),
            next_step=step_index + 1 if outcome.correct and not is_last else None,
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        fields = {
            "puzzle_id": puzzle_id,
            "step": step_index,
            "correct": result.correct,
            "matched_rules": result.diagnosis.matched_rules,
            "latency_ms": latency_ms,
        }
        check_log.info(
            "puzzle_check puzzle_id=%s step=%s correct=%s matched_rules=%s latency_ms=%s",
            puzzle_id,
            step_index,
            result.correct,
            ",".join(result.diagnosis.matched_rules) or "-",
            latency_ms,
            extra={"puzzle_check": fields},
        )
        players = self.players
        if player_id is not None and players is not None:
            details = puzzle_type.attempt_details(puzzle, step_index)
            if context is not None:
                details = {**details, "context": context}
            record = AttemptRecord(
                puzzle_id=puzzle.puzzle_id,
                generator_version=puzzle.generator_version,
                game=puzzle_type.game,
                level=puzzle.level,
                step_index=step_index,
                answer=answer,
                correct=outcome.correct,
                matched_rules=list(outcome.matched_rules),
                error_pattern_ids=list(outcome.error_pattern_ids),
                reteach_topic_id=outcome.reteach_topic_id,
                topic_ids=puzzle_type.step_topic_ids(puzzle, step_index),
                details=details,
            )
            self._store(players, lambda: players.record_attempt(player_id, record))
        return result

    def hint(
        self, puzzle_id: str, step_index: int, tier: int, player_id: uuid.UUID | None = None
    ) -> HintOut:
        """One hint tier, counted from 1. What each tier gives away is the type's business.

        With a player id the request is stored; the hint is the same either way.
        """
        puzzle_type, puzzle = self._rebuild(puzzle_id)
        self._require_step(puzzle, step_index)
        tiers = puzzle_type.hint_tiers(puzzle, step_index)
        if not 1 <= tier <= tiers:
            raise HintTierNotFound(tier, tiers)
        text = puzzle_type.hint(puzzle, step_index, tier)
        players = self.players
        if player_id is not None and players is not None:
            self._store(
                players, lambda: players.record_hint(player_id, puzzle_id, step_index, tier)
            )
        return HintOut(tier=tier, text=text)

    @staticmethod
    def _store(players: PlayerService, write: Callable[[], None]) -> None:
        """Run one history write. If the database refuses it, the child still gets
        their answer: the failure is logged (without the player id) and dropped."""
        try:
            write()
        except SQLAlchemyError:
            players.session.rollback()
            logger.exception("Could not store practice history; the response is unaffected")

    def _rebuild(self, puzzle_id: str) -> tuple[PuzzleType, InternalPuzzle]:
        """The type an id belongs to (from its prefix), and the puzzle it names."""
        puzzle_type, raw = self._type_of(puzzle_id)
        return puzzle_type, self._regenerate(puzzle_type, raw, puzzle_id)

    def _type_of(self, puzzle_id: str) -> tuple[PuzzleType, RawPuzzleId]:
        """The loaded type an id belongs to. The checksum is checked; nothing else yet."""
        try:
            raw = split_id(puzzle_id)
        except InvalidPuzzleId as error:
            raise PuzzleNotFound(puzzle_id) from error
        registered = self.runtime.registry.by_code(raw.type_code)
        if registered is None:
            raise PuzzleNotFound(puzzle_id)
        return self.runtime.require(registered.game), raw

    @staticmethod
    def _regenerate(puzzle_type: PuzzleType, raw: RawPuzzleId, puzzle_id: str) -> InternalPuzzle:
        try:
            return regenerate(puzzle_type, raw, puzzle_id)
        except OutdatedPuzzleId as error:
            raise PuzzleVersionGone(puzzle_id, puzzle_type.generator_version) from error
        except (InvalidPuzzleId, ValueError, PuzzleRejected) as error:
            # Malformed, tampered with, or naming a puzzle this generator never makes.
            raise PuzzleNotFound(puzzle_id) from error

    @staticmethod
    def _require_step(puzzle: InternalPuzzle, step_index: int) -> None:
        if not 0 <= step_index < len(puzzle.steps):
            raise StepNotFound(puzzle.puzzle_id, step_index, len(puzzle.steps))

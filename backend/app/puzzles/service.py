"""Puzzles for Python callers and for the HTTP layer. No FastAPI in here.

Stateless: nothing about a puzzle is stored. A puzzle is rebuilt from its
puzzle_id on every call and verified again before it is used.

    runtime = PuzzleRuntime()                  # one per process
    runtime.refresh(taxonomy_service)          # resolves the catalog when needed
    service = PuzzleService(taxonomy_service, runtime.require_catalog())
    puzzle = service.new_puzzle(level=1, length=3)
    result = service.check(puzzle.puzzle_id, 0, 19)
"""

import hashlib
import logging
import random
import secrets
import time

from app.puzzles.diagnoser import diagnose
from app.puzzles.ids import MAX_SEED, InvalidPuzzleId, OutdatedPuzzleId
from app.puzzles.levels import GENERATOR_VERSION
from app.puzzles.misconceptions import MisconceptionCatalog, MisconceptionResolutionError
from app.puzzles.models import Puzzle
from app.puzzles.schemas import (
    CheckResult,
    DiagnosisPublic,
    HintOut,
    PuzzlePublic,
    PuzzleStepPublic,
    ReteachTopic,
)
from app.puzzles.taxonomy_link import first_step_back, load_catalog, topic_exists
from app.puzzles.verified import PuzzleRejected, generate_verified, regenerate
from app.taxonomy.service import TaxonomyService, TopicNotFound

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

    def __init__(self, puzzle_id: str) -> None:
        super().__init__(f"Puzzle {puzzle_id} is from an older generator version")
        self.puzzle_id = puzzle_id
        self.current_version = GENERATOR_VERSION


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


class PuzzlesUnavailable(PuzzleError):
    """The mistake-rule mapping could not be resolved against the taxonomy."""


class PuzzleRuntime:
    """The resolved misconception catalog, kept for the life of the process.

    Resolving it reads the database, so it is done once and reused. `refresh`
    resolves it again only when the prerequisite graph has been reloaded since
    (a re-import), which it can tell from the graph's version stamp.
    """

    def __init__(self) -> None:
        self.catalog: MisconceptionCatalog | None = None
        self.error: str | None = None
        # How many times the catalog has been resolved. For tests and for curiosity.
        self.load_count = 0
        self._loaded = False
        self._graph_version: object = None

    def refresh(self, taxonomy: TaxonomyService) -> None:
        version = taxonomy.graph.version
        if self._loaded and version == self._graph_version:
            return
        self.load_count += 1
        self._loaded, self._graph_version = True, version
        try:
            self.catalog, self.error = load_catalog(taxonomy), None
        except (MisconceptionResolutionError, TopicNotFound) as error:
            self.catalog, self.error = None, str(error)
            logger.warning("Puzzles are unavailable: the rule mapping did not resolve: %s", error)

    def require_catalog(self) -> MisconceptionCatalog:
        if self.catalog is None:
            raise PuzzlesUnavailable(
                "Puzzles are unavailable: the taxonomy does not have the topics they need."
            )
        return self.catalog


def shuffled_options(puzzle_id: str, step_index: int, values: list[int]) -> list[int]:
    """The answer options in an order fixed by the puzzle id and step, so a reload matches."""
    digest = hashlib.sha256(f"{puzzle_id}:{step_index}".encode()).digest()
    options = sorted(values)
    random.Random(int.from_bytes(digest[:8], "big")).shuffle(options)
    return options


def to_public(puzzle: Puzzle) -> PuzzlePublic:
    """The child-facing view: equations and options, no answers, rules or hint text."""
    return PuzzlePublic(
        puzzle_id=puzzle.puzzle_id,
        level=puzzle.level,
        length=len(puzzle.steps),
        topic_ids=list(puzzle.topic_ids),
        steps=[
            PuzzleStepPublic(
                index=index,
                equation=step.equation,
                options=shuffled_options(
                    puzzle.puzzle_id,
                    index,
                    [step.answer, *(distractor.value for distractor in step.distractors)],
                ),
                hint_tiers=len(step.hints),
            )
            for index, step in enumerate(puzzle.steps)
        ],
    )


class PuzzleService:
    def __init__(self, taxonomy: TaxonomyService, catalog: MisconceptionCatalog) -> None:
        self.taxonomy = taxonomy
        self.catalog = catalog
        self._topic_exists = topic_exists(taxonomy)
        self._step_back = first_step_back(taxonomy)

    def new_puzzle(self, level: int, length: int = 3, seed: int | None = None) -> PuzzlePublic:
        """A new verified puzzle. Without a seed, one is drawn at random.

        Raises verified.PuzzleGenerationFailed if every attempt fails.
        """
        if seed is None:
            seed = secrets.randbelow(MAX_SEED + 1)
        puzzle = generate_verified(
            seed, level, length, catalog=self.catalog, topic_exists=self._topic_exists
        )
        return to_public(puzzle)

    def get_puzzle(self, puzzle_id: str) -> PuzzlePublic:
        return to_public(self._rebuild(puzzle_id))

    def check(self, puzzle_id: str, step_index: int, answer: int) -> CheckResult:
        """Check one answer. Never reveals the right answer when the child is wrong."""
        started = time.perf_counter()
        puzzle = self._rebuild(puzzle_id)
        self._require_step(puzzle, step_index)
        diagnosis = diagnose(
            puzzle, step_index, answer, catalog=self.catalog, step_back=self._step_back
        )

        reteach = None
        if diagnosis.reteach_topic_id is not None:
            summaries = self.taxonomy.get_summaries([diagnosis.reteach_topic_id])
            summary = summaries.get(diagnosis.reteach_topic_id)
            if summary is not None:
                reteach = ReteachTopic(id=summary.id, name=summary.name)

        is_last = step_index == len(puzzle.steps) - 1
        result = CheckResult(
            correct=diagnosis.correct,
            feedback="correct" if diagnosis.correct else "try_again",
            diagnosis=DiagnosisPublic(
                matched_rules=[rule.value for rule in diagnosis.matched_rules],
                unrecognized=diagnosis.unrecognized,
                reteach_topic=reteach,
            ),
            next_step=step_index + 1 if diagnosis.correct and not is_last else None,
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
        return result

    def hint(self, puzzle_id: str, step_index: int, tier: int) -> HintOut:
        """One hint tier, from 1 (meaning) to 3 (worked step, which shows the answer)."""
        puzzle = self._rebuild(puzzle_id)
        self._require_step(puzzle, step_index)
        hints = puzzle.steps[step_index].hints
        if not 1 <= tier <= len(hints):
            raise HintTierNotFound(tier, len(hints))
        return HintOut(tier=tier, text=hints[tier - 1])

    def _rebuild(self, puzzle_id: str) -> Puzzle:
        try:
            return regenerate(puzzle_id, catalog=self.catalog, topic_exists=self._topic_exists)
        except OutdatedPuzzleId as error:
            raise PuzzleVersionGone(puzzle_id) from error
        except (InvalidPuzzleId, ValueError, PuzzleRejected) as error:
            # Malformed, tampered with, or naming a puzzle this generator never makes.
            raise PuzzleNotFound(puzzle_id) from error

    @staticmethod
    def _require_step(puzzle: Puzzle, step_index: int) -> None:
        if not 0 <= step_index < len(puzzle.steps):
            raise StepNotFound(puzzle.puzzle_id, step_index, len(puzzle.steps))

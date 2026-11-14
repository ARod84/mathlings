"""Today's Puzzle: the same puzzle for everyone on the same day, in three levels.

Like a daily crossword. Nothing is stored and no AI is involved: the puzzle is
an ordinary puzzle of one of the server-side games, with a seed derived from
the date, so every device that asks for the same date, game and level gets
the same puzzle id. The existing check and hint routes work on it unchanged.

    choose(date(2026, 3, 10), level=2)       -> DailyChoice(game="sequences", seed=...)
    daily_puzzle(runtime, date, level)       -> that game's public puzzle

The rotation is a fixed schedule over the games whose puzzles the server
makes, by the number of days since EPOCH. Number Pyramid is built in the
browser, so it is not in the rotation for now.

The date is the child's: it comes from their device, so "today" is their
local day. The server accepts it within a day of its own UTC date, which
covers every timezone (see `date_in_window`).

No secret goes into the seed. The answers are not secret (see the root
README), so there is nothing to protect against.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.puzzles.core import PublicPuzzle
from app.puzzles.core.ids import MAX_SEED
from app.puzzles.core.verified import generate_verified
from app.puzzles.service import PuzzleRuntime

# The games, in the order they take turns. Day 0 (EPOCH) is the first one.
ROTATION: tuple[str, ...] = ("missing-number", "sequences", "sum-grid")
# A fixed date the day number counts from. Changing it changes every day's game.
EPOCH = date(2026, 1, 1)
# How far from the server's UTC date a requested date may be, in days.
DATE_WINDOW_DAYS = 1


@dataclass(frozen=True)
class DailyChoice:
    day: date
    game: str
    level: int
    seed: int


def utc_today() -> date:
    """The server's date. A function, so a test can stand still in time."""
    return datetime.now(UTC).date()


def game_for(day: date) -> str:
    """Which game `day` is: the rotation, by days since EPOCH (negative days work too)."""
    return ROTATION[(day - EPOCH).days % len(ROTATION)]


def daily_seed(day: date, game: str, level: int) -> int:
    """The seed for one day's puzzle at one level. SHA-256 of a fixed text, in the seed range."""
    text = f"daily:{day.isoformat()}:{game}:{level}"
    return int(hashlib.sha256(text.encode("ascii")).hexdigest(), 16) % (MAX_SEED + 1)


def choose(day: date, level: int) -> DailyChoice:
    game = game_for(day)
    return DailyChoice(day, game, level, daily_seed(day, game, level))


def date_in_window(day: date, today: date | None = None) -> bool:
    """True if `day` is within DATE_WINDOW_DAYS of the server's UTC date, either way."""
    today = utc_today() if today is None else today
    return abs(day - today) <= timedelta(days=DATE_WINDOW_DAYS)


def daily_puzzle(runtime: PuzzleRuntime, day: date, level: int) -> PublicPuzzle:
    """The day's puzzle at `level`, with the game's default parameters, verified.

    Pure generation: nothing is read from the database. Raises the same
    errors as any new puzzle (PuzzlesUnavailable, PuzzleGenerationFailed) and
    ValueError for a level the game does not have.
    """
    choice = choose(day, level)
    puzzle_type = runtime.require(choice.game)
    if level not in puzzle_type.levels:
        raise ValueError(f"{choice.game} has no level {level}")
    return puzzle_type.to_public(generate_verified(puzzle_type, choice.seed, level))

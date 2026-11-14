"""Today's Puzzle on HTTP. One route; the logic is in app/puzzles/daily.py.

    GET /api/v1/daily?date=YYYY-MM-DD&level=1|2|3   -> {date, game, level, puzzle}

`puzzle` is the public shape of the day's game, so the browser plays it with
the ordinary check and hint routes. The response model is built from the
registry, like the puzzle routes' (one shape per game, told apart by `game`).

This route touches no database: the puzzle types were loaded at startup (or
by the first puzzle request after a re-import), and generation is pure. A
statement-budget test holds it to zero statements.
"""

from datetime import date as Date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, create_model

from app.api.v1.puzzles import UNAVAILABLE, public_puzzle_type
from app.puzzles import daily
from app.puzzles.registry import PuzzleRegistry

DAILY_TAG = "Daily"


class DailyPuzzleBase(BaseModel):
    """The fields that do not depend on which games exist. `puzzle` is added per registry."""

    date: Date = Field(description="The day asked for, as the device gave it.")
    game: str = Field(description="The game of the day: the rotation in app/puzzles/daily.py.")
    level: int = Field(description="1 (easy), 2 (medium) or 3 (hard).")


def daily_model(registry: PuzzleRegistry) -> type[DailyPuzzleBase]:
    """DailyPuzzle: the base fields plus `puzzle`, one of the registered games' public shapes."""
    return create_model(
        "DailyPuzzle",
        __base__=DailyPuzzleBase,
        puzzle=(public_puzzle_type(registry), Field(description="The day's puzzle at `level`.")),
    )


def _date_rejected(day: Date, today: Date) -> RequestValidationError:
    """A 422 in the same shape as any other query parameter that fails validation."""
    return RequestValidationError(
        [
            {
                "type": "date_out_of_window",
                "loc": ("query", "date"),
                "msg": (
                    f"Input should be within {daily.DATE_WINDOW_DAYS} day of the server's date, "
                    f"{today.isoformat()} (UTC)"
                ),
                "input": day.isoformat(),
            }
        ]
    )


def build_router(registry: PuzzleRegistry) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=[DAILY_TAG])
    model = daily_model(registry)

    @router.get(
        "/daily",
        response_model=model,
        responses=UNAVAILABLE,
        summary="Today's Puzzle: the same puzzle for everyone, at one of three levels",
        description=(
            "Deterministic: the same `date`, game and `level` always give the same puzzle id, "
            "on every server. The game follows a fixed rotation by day; the puzzle uses the "
            "game's default parameters. `date` is the child's local date, from their device, "
            "and must be within a day of the server's UTC date (anything else is a 422). "
            'Play it with the ordinary check and hint routes; send `context: "daily"` with '
            "each check so the attempt is marked as Today's Puzzle."
        ),
    )
    def get_daily(
        request: Request,
        date: Annotated[
            Date,
            Query(description="YYYY-MM-DD, the child's local date. Within a day of UTC today."),
        ],
        level: Annotated[int, Query(ge=1, le=3, description="1 easy, 2 medium, 3 hard.")],
    ) -> Any:
        today = daily.utc_today()
        if not daily.date_in_window(date, today):
            raise _date_rejected(date, today)
        puzzle = daily.daily_puzzle(request.app.state.puzzles, date, level)
        return model(date=date, game=puzzle.game, level=level, puzzle=puzzle)

    return router

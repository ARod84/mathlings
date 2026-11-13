"""Puzzle routes. Thin on purpose: parse the request, call PuzzleService."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.v1.players import OptionalPlayer
from app.api.v1.taxonomy import NOT_LOADED, Service
from app.players.service import PlayerService
from app.puzzles.schemas import (
    CheckRequest,
    CheckResult,
    HintOut,
    NewPuzzleRequest,
    PuzzleGoneBody,
    PuzzleNotFoundBody,
    PuzzlePublic,
)
from app.puzzles.service import PuzzleService
from app.taxonomy.schemas import ErrorBody


def get_puzzle_service(request: Request, taxonomy: Service) -> PuzzleService:
    # `taxonomy` has already made sure the graph is current. The catalog is
    # resolved once per process and again only after the graph reloads.
    runtime = request.app.state.puzzles
    runtime.refresh(taxonomy)
    # History is written on the request's own session, so in its transaction.
    return PuzzleService(
        taxonomy, runtime.require_catalog(), players=PlayerService(taxonomy.session)
    )


Puzzles = Annotated[PuzzleService, Depends(get_puzzle_service)]

UNAVAILABLE = {
    503: {"model": ErrorBody, "description": "Puzzles cannot be served right now"},
}
PUZZLE_ERRORS = {
    404: {
        "model": PuzzleNotFoundBody,
        "description": "Unknown puzzle id, step or hint tier",
    },
    410: {"model": PuzzleGoneBody, "description": "The puzzle is from an older generator version"},
    **UNAVAILABLE,
}

# Every puzzle route takes the optional X-Player-Id header and rejects a
# malformed one. Only check and hint store anything, and only when it is sent.
router = APIRouter(prefix="/api/v1/puzzles", tags=["Puzzles"], responses=NOT_LOADED)


@router.post(
    "/missing-number",
    response_model=PuzzlePublic,
    status_code=status.HTTP_201_CREATED,
    responses=UNAVAILABLE,
    summary="Start a new missing-number chain",
)
def new_missing_number_puzzle(
    body: NewPuzzleRequest, puzzles: Puzzles, _player_id: OptionalPlayer
) -> PuzzlePublic:
    return puzzles.new_puzzle(body.level, body.length, body.seed)


@router.get(
    "/{puzzle_id}",
    response_model=PuzzlePublic,
    responses=PUZZLE_ERRORS,
    summary="Rebuild a puzzle from its id",
)
def get_puzzle(puzzle_id: str, puzzles: Puzzles, _player_id: OptionalPlayer) -> PuzzlePublic:
    return puzzles.get_puzzle(puzzle_id)


@router.post(
    "/{puzzle_id}/steps/{index}/check",
    response_model=CheckResult,
    responses=PUZZLE_ERRORS,
    summary="Check an answer to one step",
)
def check_step(
    puzzle_id: str, index: int, body: CheckRequest, puzzles: Puzzles, player_id: OptionalPlayer
) -> CheckResult:
    return puzzles.check(puzzle_id, index, body.answer, player_id=player_id)


@router.get(
    "/{puzzle_id}/steps/{index}/hints/{tier}",
    response_model=HintOut,
    responses=PUZZLE_ERRORS,
    summary="One hint tier for a step",
)
def get_hint(
    puzzle_id: str, index: int, tier: int, puzzles: Puzzles, player_id: OptionalPlayer
) -> HintOut:
    return puzzles.hint(puzzle_id, index, tier, player_id=player_id)

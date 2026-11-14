"""Puzzle routes, the same four for every game. Thin: parse the request, call PuzzleService.

    POST /api/v1/puzzles/{game}                                  a new puzzle
    GET  /api/v1/puzzles/{puzzle_id}                             the type comes from the id
    POST /api/v1/puzzles/{puzzle_id}/steps/{index}/check
    GET  /api/v1/puzzles/{puzzle_id}/steps/{index}/hints/{tier}

The router is built from a registry, because two things in the OpenAPI
document depend on which games exist: the body of a new-puzzle request (each
game has its own) and the puzzle that comes back (one shape per game, told
apart by its `game` field).
"""

import operator
from functools import reduce
from json import JSONDecodeError
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import Field, ValidationError

from app.api.v1.players import OptionalPlayer
from app.api.v1.taxonomy import NOT_LOADED, Service
from app.players.service import PlayerService
from app.puzzles.core import NewPuzzleBody, PublicPuzzle
from app.puzzles.core.schemas import (
    CheckRequest,
    CheckResult,
    HintOut,
    PuzzleGoneBody,
    PuzzleNotFoundBody,
    UnknownGameBody,
)
from app.puzzles.registry import PuzzleRegistry
from app.puzzles.service import PuzzleService
from app.puzzles.types.missing_number.levels import GAME as MISSING_NUMBER
from app.puzzles.types.missing_number.schemas import NewPuzzleRequest, PuzzlePublic
from app.taxonomy.schemas import ErrorBody


def get_puzzle_service(request: Request, taxonomy: Service) -> PuzzleService:
    # `taxonomy` has already made sure the graph is current. The puzzle types
    # are loaded once per process and again only after the graph reloads.
    runtime = request.app.state.puzzles
    runtime.refresh(taxonomy)
    # History is written on the request's own session, so in its transaction.
    return PuzzleService(taxonomy, runtime, players=PlayerService(taxonomy.session))


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
UNKNOWN_GAME = {404: {"model": UnknownGameBody, "description": "No such game"}}
_SCHEMA_REF = "#/components/schemas/{model}"


def public_puzzle_type(registry: PuzzleRegistry) -> Any:
    """What a puzzle response is: one of the games' public shapes, told apart by `game`."""
    models = [puzzle_type.public_model for puzzle_type in registry]
    if len(models) == 1:
        # A discriminated union needs at least two members.
        return models[0]
    return Annotated[reduce(operator.or_, models), Field(discriminator="game")]


def _request_body_schema(registry: PuzzleRegistry) -> dict[str, Any]:
    """The new-puzzle request body for the OpenAPI document: one schema per game."""
    # Two games may share a request model; it is listed once.
    names = list(dict.fromkeys(puzzle_type.request_model.__name__ for puzzle_type in registry))
    refs = [{"$ref": _SCHEMA_REF.format(model=name)} for name in names]
    schema = refs[0] if len(refs) == 1 else {"oneOf": refs}
    return {
        "required": True,
        "description": "The body for the game named in the path. Each game has its own: "
        + ", ".join(f"`{t.game}` takes {t.request_model.__name__}" for t in registry)
        + ".",
        "content": {"application/json": {"schema": schema}},
    }


def add_request_schemas(document: dict[str, Any], registry: PuzzleRegistry) -> None:
    """Put every game's request model among the document's schemas.

    FastAPI only lists the models it sees in a route's signature, and the
    body of POST /puzzles/{game} is validated by hand (it depends on the
    path), so the models it refers to are added here. Safe to call twice.

    They are written the way FastAPI writes the ones it lists itself: a field
    whose default is null carries no `default` at all. Client generators read
    a `default` as "always there", and would mark an optional `seed` as required.
    """
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    for puzzle_type in registry:
        model = puzzle_type.request_model
        schema = _without_null_defaults(model.model_json_schema(ref_template=_SCHEMA_REF))
        for name, definition in schema.pop("$defs", {}).items():
            schemas.setdefault(name, definition)
        schemas.setdefault(model.__name__, schema)


def _without_null_defaults(schema: Any) -> Any:
    """A JSON schema with every `"default": null` taken out, at any depth."""
    if isinstance(schema, list):
        return [_without_null_defaults(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    return {
        key: _without_null_defaults(value)
        for key, value in schema.items()
        if not (key == "default" and value is None)
    }


def build_router(registry: PuzzleRegistry) -> APIRouter:
    # Every puzzle route takes the optional X-Player-Id header and rejects a
    # malformed one. Only check and hint store anything, and only when it is sent.
    router = APIRouter(prefix="/api/v1/puzzles", tags=["Puzzles"], responses=NOT_LOADED)
    public_puzzle = public_puzzle_type(registry)

    async def new_puzzle_request(game: str, request: Request) -> NewPuzzleBody:
        """The request body, validated as the model of the game in the path.

        An unknown game is a 404 (main.py) before the body is looked at.
        """
        model = registry.by_game(game).request_model
        try:
            return model.model_validate(await request.json())
        except JSONDecodeError as error:
            raise RequestValidationError(
                [{"type": "json_invalid", "loc": ("body",), "msg": "Not valid JSON", "input": {}}]
            ) from error
        except ValidationError as error:
            raise RequestValidationError(
                [
                    {**problem, "loc": ("body", *problem["loc"])}
                    for problem in error.errors(include_url=False, include_context=False)
                ]
            ) from error

    if MISSING_NUMBER in registry.games:
        # The route this API started with, from when chains were the only game.
        # Declared before /{game}, so it is the one that answers this path.
        @router.post(
            f"/{MISSING_NUMBER}",
            response_model=PuzzlePublic,
            status_code=status.HTTP_201_CREATED,
            responses=UNAVAILABLE,
            summary="Start a new missing-number chain",
            description="Deprecated spelling of `POST /api/v1/puzzles/{game}` with "
            "`game` = `missing-number`. Same URL, same body, same answer: a client "
            "written against either one keeps working when this entry is removed.",
            deprecated=True,
        )
        def new_missing_number_puzzle(
            body: NewPuzzleRequest, puzzles: Puzzles, _player_id: OptionalPlayer
        ) -> PublicPuzzle:
            return puzzles.new_puzzle_from(MISSING_NUMBER, body)

    @router.post(
        "/{game}",
        response_model=public_puzzle,
        status_code=status.HTTP_201_CREATED,
        responses={**UNKNOWN_GAME, **UNAVAILABLE},
        summary="Start a new puzzle of a game",
        openapi_extra={"requestBody": _request_body_schema(registry)},
    )
    def new_puzzle(
        game: str,
        body: Annotated[NewPuzzleBody, Depends(new_puzzle_request)],
        puzzles: Puzzles,
        _player_id: OptionalPlayer,
    ) -> PublicPuzzle:
        return puzzles.new_puzzle_from(game, body)

    @router.get(
        "/{puzzle_id}",
        response_model=public_puzzle,
        responses=PUZZLE_ERRORS,
        summary="Rebuild a puzzle from its id",
    )
    def get_puzzle(puzzle_id: str, puzzles: Puzzles, _player_id: OptionalPlayer) -> PublicPuzzle:
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
        return puzzles.check(
            puzzle_id, index, body.answer, player_id=player_id, context=body.context
        )

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

    return router

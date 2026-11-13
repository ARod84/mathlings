"""Player routes and the X-Player-Id header. Thin: parse the request, call PlayerService.

The header carries a UUIDv4 that the browser made. It is a pseudonymous
identifier, NOT authentication: see app/players/service.py. No cookie is set,
and nothing about the request (IP address, user agent) is stored.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import UUID4
from sqlmodel import Session

from app.api.v1.taxonomy import get_session
from app.players.schemas import PlayerNotFoundBody, PlayerSummary
from app.players.service import PlayerService
from app.taxonomy.schemas import ErrorBody

PLAYER_HEADER = "X-Player-Id"
_DESCRIPTION = (
    "A random UUID version 4 that the browser made and keeps. A pseudonymous id, not a login."
)


def optional_player_id(
    player_id: Annotated[
        UUID4 | None,
        Header(
            alias=PLAYER_HEADER,
            description=_DESCRIPTION + " Leave out to play without anything being stored.",
        ),
    ] = None,
) -> uuid.UUID | None:
    return player_id


def required_player_id(
    player_id: Annotated[UUID4, Header(alias=PLAYER_HEADER, description=_DESCRIPTION)],
) -> uuid.UUID:
    return player_id


# Missing: None, and nothing is stored. Malformed or not version 4: 422.
OptionalPlayer = Annotated[uuid.UUID | None, Depends(optional_player_id)]
RequiredPlayer = Annotated[uuid.UUID, Depends(required_player_id)]


class PlayersUnavailable(Exception):
    """The player tables do not exist yet (the migration has not been run)."""


def get_player_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> PlayerService:
    if not request.app.state.players_ready():
        raise PlayersUnavailable("The player tables are not ready. Run the migration.")
    return PlayerService(session)


Players = Annotated[PlayerService, Depends(get_player_service)]

UNAVAILABLE = {503: {"model": ErrorBody, "description": "The player tables do not exist yet"}}

router = APIRouter(prefix="/api/v1/players", tags=["Players"], responses=UNAVAILABLE)


@router.get(
    "/me/summary",
    response_model=PlayerSummary,
    responses={404: {"model": PlayerNotFoundBody, "description": "Nothing is stored for this id"}},
    summary="Practice summary for the player in the header",
)
def get_summary(player_id: RequiredPlayer, players: Players) -> PlayerSummary:
    return players.summary(player_id)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the player and all of their history",
)
def delete_player(player_id: RequiredPlayer, players: Players) -> Response:
    # 204 for an unknown id too: afterwards nothing is stored either way.
    players.delete(player_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

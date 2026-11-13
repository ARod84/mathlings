"""Player routes and the X-Player-Id header. Thin: parse the request, call PlayerService.

The header carries a UUIDv4 that the browser made. It is a pseudonymous
identifier, NOT authentication: see app/players/service.py. No cookie is set,
and nothing about the request (IP address, user agent) is stored.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import UUID4
from sqlmodel import Session

from app.adaptive.bkt import TopicMastery
from app.adaptive.schemas import NamedMastery, NextPuzzle, TopicMasteryOut
from app.adaptive.service import AdaptiveService
from app.api.v1.taxonomy import NOT_LOADED, Service, get_session
from app.players.schemas import PlayerNotFoundBody, PlayerSummary
from app.players.service import PlayerService, utc
from app.puzzles.registry import PuzzleRegistry
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


def get_adaptive_service(players: Players) -> AdaptiveService:
    # Same session as the request, and the same "are the tables there" check.
    return AdaptiveService(players.session)


Adaptive = Annotated[AdaptiveService, Depends(get_adaptive_service)]


def _mastery_out(mastery: TopicMastery) -> TopicMasteryOut:
    return TopicMasteryOut(
        topic_id=mastery.topic_id,
        level=mastery.level,
        p_known=round(mastery.p_known, 4),
        observations=mastery.observations,
        last_practised=utc(mastery.last_practised) if mastery.last_practised else None,
    )


UNAVAILABLE = {503: {"model": ErrorBody, "description": "The player tables do not exist yet"}}


def build_router(registry: PuzzleRegistry) -> APIRouter:
    """The player routes. Built from the registry: /me/next takes any registered game."""
    router = APIRouter(prefix="/api/v1/players", tags=["Players"], responses=UNAVAILABLE)
    # A Literal of the registered games, so the document lists them and any other is a 422.
    game_name = Literal[tuple(registry.games)]

    @router.get(
        "/me/summary",
        response_model=PlayerSummary,
        responses={
            404: {"model": PlayerNotFoundBody, "description": "Nothing is stored for this id"}
        },
        summary="Practice summary for the player in the header",
    )
    def get_summary(
        player_id: RequiredPlayer, players: Players, adaptive: Adaptive
    ) -> PlayerSummary:
        summary = players.summary(player_id)
        mastery = adaptive.mastery(player_id)
        summary.mastery = [
            _mastery_out(mastery[key]) for key in sorted(mastery, key=lambda k: k[::-1])
        ]
        return summary

    @router.get(
        "/me/next",
        response_model=NextPuzzle,
        responses=NOT_LOADED,
        summary="What the player in the header should play next, and why",
    )
    def get_next(
        player_id: RequiredPlayer,
        adaptive: Adaptive,
        taxonomy: Service,
        game: Annotated[
            game_name,
            Query(
                description="The game to recommend for. Only Missing Number Chains adapts so "
                "far; any other game gets its default, with reason_code `no_policy`."
            ),
        ],
    ) -> NextPuzzle:
        """A player with no stored attempts, known or not, gets the cold start.

        `reason`, `focus_rule` and `mastery` are for adults and for development.
        Nothing in this response is meant to be shown to a child.
        """
        recommendation = adaptive.recommend(player_id, registry.by_game(game))
        # The recommended level's topics first (primary first), then the rest by level.
        at_level = [key for key in recommendation.mastery if key[1] == recommendation.level]
        others = sorted(
            (key for key in recommendation.mastery if key[1] != recommendation.level),
            key=lambda key: key[::-1],
        )
        names = (
            taxonomy.get_summaries({topic_id for topic_id, _level in recommendation.mastery})
            if recommendation.mastery
            else {}
        )
        return NextPuzzle(
            level=recommendation.level,
            length=recommendation.length,
            reason_code=recommendation.reason_code,
            reason=recommendation.reason,
            focus_rule=recommendation.focus_rule,
            focus=recommendation.focus,
            params=recommendation.params,
            mastery=[
                NamedMastery(
                    topic_id=key[0],
                    name=names[key[0]].name if key[0] in names else key[0],
                    level=key[1],
                    p_known=round(recommendation.mastery[key].p_known, 4),
                    observations=recommendation.mastery[key].observations,
                )
                for key in [*at_level, *others]
            ],
        )

    @router.delete(
        "/me",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete the player and all of their history",
    )
    def delete_player(player_id: RequiredPlayer, players: Players) -> Response:
        # 204 for an unknown id too: afterwards nothing is stored either way.
        players.delete(player_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router

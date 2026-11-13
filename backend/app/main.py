import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from sqlmodel import Session

from app.api.v1 import players as players_api
from app.api.v1 import puzzles as puzzles_api
from app.api.v1 import taxonomy as taxonomy_api
from app.config import Settings, get_settings
from app.db import make_engine
from app.models import Player, Topic
from app.players.service import PlayerNotFound
from app.puzzles.service import (
    HintTierNotFound,
    PuzzleNotFound,
    PuzzleRuntime,
    PuzzlesUnavailable,
    PuzzleVersionGone,
    StepNotFound,
)
from app.puzzles.verified import PuzzleGenerationFailed
from app.taxonomy.graph import PrerequisiteGraph, taxonomy_graph
from app.taxonomy.schemas import Health
from app.taxonomy.service import (
    ResearchNotFound,
    TaxonomyNotLoaded,
    TaxonomyService,
    TopicNotFound,
    reload_graph,
)

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {"name": "Topics", "description": "Browse and read the learning topics."},
    {
        "name": "Prerequisite graph",
        "description": "What a topic requires first, what it unlocks, and where to step back to.",
    },
    {
        "name": "Teaching",
        "description": "Typical mistakes and teaching research for a topic.",
    },
    {
        "name": "Puzzles",
        "description": "Missing-number chains. Stateless: a puzzle is rebuilt from its id.",
    },
    {
        "name": "Players",
        "description": "Anonymous practice history, kept only when the browser sends "
        "X-Player-Id. The id is a pseudonymous identifier, not authentication.",
    },
    {"name": "Meta", "description": "Service health, dataset version and attribution."},
]


def create_app(settings: Settings | None = None, graph: PrerequisiteGraph | None = None) -> FastAPI:
    settings = settings or get_settings()
    graph = graph if graph is not None else taxonomy_graph

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        app.state.engine = engine
        app.state.graph = graph
        app.state.puzzles = PuzzleRuntime()

        def taxonomy_ready() -> bool:
            # Checked once it is true, never again: tables do not disappear.
            if not app.state.has_tables:
                app.state.has_tables = inspect(engine).has_table(Topic.__tablename__)
            return app.state.has_tables

        def players_ready() -> bool:
            # The same idea for the player tables (migration 0002).
            if not app.state.has_player_tables:
                app.state.has_player_tables = inspect(engine).has_table(Player.__tablename__)
            return app.state.has_player_tables

        app.state.has_tables = False
        app.state.taxonomy_ready = taxonomy_ready
        app.state.has_player_tables = False
        app.state.players_ready = players_ready
        players_ready()
        # Load the prerequisite graph once, up front. An empty or missing
        # database is not an error here: /health reports it.
        if taxonomy_ready():
            with Session(engine) as session:
                reload_graph(session, graph)
                # The mistake-rule catalog is resolved here, once, next to the graph.
                if graph.topic_count:
                    app.state.puzzles.refresh(TaxonomyService(session, graph))
        yield
        engine.dispose()

    app = FastAPI(
        title="Mathlings API",
        version="0.1.0",
        description=(
            "The learning topics behind the Mathlings games (what each topic requires first, "
            "and the mistakes children typically make) and the puzzles built on them."
        ),
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(TopicNotFound)
    def topic_not_found(_request: Request, error: TopicNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "Topic not found", "topic_id": error.topic_id}
        )

    @app.exception_handler(ResearchNotFound)
    def research_not_found(_request: Request, error: ResearchNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": "Topic has no research", "topic_id": error.topic_id},
        )

    @app.exception_handler(TaxonomyNotLoaded)
    def taxonomy_not_loaded(_request: Request, error: TaxonomyNotLoaded) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(PuzzleNotFound)
    def puzzle_not_found(_request: Request, error: PuzzleNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "Puzzle not found", "puzzle_id": error.puzzle_id}
        )

    @app.exception_handler(PuzzleVersionGone)
    def puzzle_version_gone(_request: Request, error: PuzzleVersionGone) -> JSONResponse:
        return JSONResponse(
            status_code=410,
            content={
                "detail": "Puzzle version is no longer available",
                "current_version": error.current_version,
            },
        )

    @app.exception_handler(StepNotFound)
    def step_not_found(_request: Request, error: StepNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": f"Step not found: this puzzle has steps 0 to {error.steps - 1}",
                "puzzle_id": error.puzzle_id,
                "step_index": error.step_index,
            },
        )

    @app.exception_handler(HintTierNotFound)
    def hint_tier_not_found(_request: Request, error: HintTierNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": f"Hint tier not found: tiers are 1 to {error.tiers}",
                "tier": error.tier,
            },
        )

    @app.exception_handler(PuzzleGenerationFailed)
    def generation_failed(_request: Request, error: PuzzleGenerationFailed) -> JSONResponse:
        # The message names the seed, level and length that could not be built.
        logger.error("Puzzle generation exhausted its retries: %s", error)
        return JSONResponse(
            status_code=503, content={"detail": "Could not make a puzzle. Please try again."}
        )

    @app.exception_handler(PuzzlesUnavailable)
    def puzzles_unavailable(_request: Request, error: PuzzlesUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(PlayerNotFound)
    def player_not_found(_request: Request, _error: PlayerNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Player not found"})

    @app.exception_handler(players_api.PlayersUnavailable)
    def players_unavailable(
        _request: Request, error: players_api.PlayersUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/health", response_model=Health, tags=["Meta"], summary="Service health")
    def health(request: Request) -> Health:
        loaded = request.app.state.taxonomy_ready() and graph.loaded and graph.topic_count > 0
        return Health(taxonomy_loaded=loaded, topic_count=graph.topic_count if loaded else 0)

    app.include_router(taxonomy_api.router)
    app.include_router(puzzles_api.router)
    app.include_router(players_api.router)
    return app


app = create_app()

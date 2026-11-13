from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from sqlmodel import Session

from app.api.v1 import taxonomy as taxonomy_api
from app.config import Settings, get_settings
from app.db import make_engine
from app.models import Topic
from app.taxonomy.graph import PrerequisiteGraph, taxonomy_graph
from app.taxonomy.schemas import Health
from app.taxonomy.service import (
    ResearchNotFound,
    TaxonomyNotLoaded,
    TopicNotFound,
    reload_graph,
)

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

        def taxonomy_ready() -> bool:
            # Checked once it is true, never again: tables do not disappear.
            if not app.state.has_tables:
                app.state.has_tables = inspect(engine).has_table(Topic.__tablename__)
            return app.state.has_tables

        app.state.has_tables = False
        app.state.taxonomy_ready = taxonomy_ready
        # Load the prerequisite graph once, up front. An empty or missing
        # database is not an error here: /health reports it.
        if taxonomy_ready():
            with Session(engine) as session:
                reload_graph(session, graph)
        yield
        engine.dispose()

    app = FastAPI(
        title="Mathlings API",
        version="0.1.0",
        description=(
            "Read-only access to the learning topics behind the Mathlings games: what each "
            "topic requires first, and the mistakes children typically make."
        ),
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
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

    @app.get("/health", response_model=Health, tags=["Meta"], summary="Service health")
    def health(request: Request) -> Health:
        loaded = request.app.state.taxonomy_ready() and graph.loaded and graph.topic_count > 0
        return Health(taxonomy_loaded=loaded, topic_count=graph.topic_count if loaded else 0)

    app.include_router(taxonomy_api.router)
    return app


app = create_app()

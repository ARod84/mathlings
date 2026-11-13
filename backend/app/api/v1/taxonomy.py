"""Read-only taxonomy routes. Thin on purpose: parse the request, call the service."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.taxonomy.schemas import (
    Depth,
    DomainCount,
    ErrorBody,
    ErrorPatternOut,
    PrerequisiteItem,
    SourceInfo,
    Strength,
    TopicDetail,
    TopicNotFoundBody,
    TopicPage,
    TopicResearch,
    TopicType,
    UnlockItem,
)
from app.taxonomy.service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    TaxonomyNotLoaded,
    TaxonomyService,
    ensure_graph_fresh,
)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> TaxonomyService:
    if not request.app.state.taxonomy_ready():
        raise TaxonomyNotLoaded(
            "The taxonomy database is not ready. Run the migration and the importer."
        )
    graph = request.app.state.graph
    ensure_graph_fresh(session, graph)
    return TaxonomyService(session, graph)


Service = Annotated[TaxonomyService, Depends(get_service)]

NOT_LOADED = {503: {"model": ErrorBody, "description": "The taxonomy has not been imported yet"}}
TOPIC_NOT_FOUND = {
    404: {"model": TopicNotFoundBody, "description": "Unknown topic id"},
    **NOT_LOADED,
}

router = APIRouter(prefix="/api/v1", responses=NOT_LOADED)


@router.get(
    "/domains",
    response_model=list[DomainCount],
    tags=["Topics"],
    summary="Domains with topic counts",
)
def list_domains(
    service: Service,
    in_scope: Annotated[
        bool,
        Query(description="true: mathematics for ages 7-12. false: prerequisite-only topics."),
    ] = True,
) -> list[DomainCount]:
    return service.list_domains(in_scope=in_scope)


@router.get(
    "/topics", response_model=TopicPage, tags=["Topics"], summary="Search and page through topics"
)
def list_topics(
    service: Service,
    domain: Annotated[str | None, Query(description="Exact domain name.")] = None,
    in_scope: Annotated[
        bool,
        Query(description="true: mathematics for ages 7-12. false: prerequisite-only topics."),
    ] = True,
    age: Annotated[
        int | None, Query(ge=0, le=18, description="Topics whose age range contains this age.")
    ] = None,
    type: Annotated[TopicType | None, Query()] = None,
    q: Annotated[
        str | None,
        Query(max_length=100, description="Case-insensitive search in name and description."),
    ] = None,
    has_research: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TopicPage:
    return service.list_topics(
        domain=domain,
        in_scope=in_scope,
        age=age,
        type=type,
        q=q,
        has_research=has_research,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/topics/{topic_id}",
    response_model=TopicDetail,
    responses=TOPIC_NOT_FOUND,
    tags=["Topics"],
    summary="One topic in full",
)
def get_topic(
    topic_id: str,
    service: Service,
    name: Annotated[
        str | None,
        Query(max_length=50, description="Child's name for the assessment prompt."),
    ] = None,
) -> TopicDetail:
    return service.get_topic(topic_id, name)


@router.get(
    "/topics/{topic_id}/prerequisites",
    response_model=list[PrerequisiteItem],
    responses=TOPIC_NOT_FOUND,
    tags=["Prerequisite graph"],
    summary="What the topic requires first",
)
def get_prerequisites(
    topic_id: str,
    service: Service,
    depth: Annotated[
        Depth, Query(description="direct: one step. all: the whole chain, nearest first.")
    ] = "direct",
    strength: Annotated[
        Strength | None, Query(description="Follow only edges of this strength.")
    ] = None,
) -> list[PrerequisiteItem]:
    return service.get_prerequisites(topic_id, depth, strength)


@router.get(
    "/topics/{topic_id}/unlocks",
    response_model=list[UnlockItem],
    responses=TOPIC_NOT_FOUND,
    tags=["Prerequisite graph"],
    summary="Topics that directly depend on this one",
)
def get_unlocks(topic_id: str, service: Service) -> list[UnlockItem]:
    return service.get_unlocks(topic_id)


@router.get(
    "/topics/{topic_id}/step-back",
    response_model=list[PrerequisiteItem],
    responses=TOPIC_NOT_FOUND,
    tags=["Prerequisite graph"],
    summary="Where to step back to, best candidate first",
)
def get_step_back(topic_id: str, service: Service) -> list[PrerequisiteItem]:
    return service.get_step_back(topic_id)


@router.get(
    "/topics/{topic_id}/error-patterns",
    response_model=list[ErrorPatternOut],
    responses=TOPIC_NOT_FOUND,
    tags=["Teaching"],
    summary="Typical mistakes and what to do about them",
)
def get_error_patterns(topic_id: str, service: Service) -> list[ErrorPatternOut]:
    return service.get_error_patterns(topic_id)


@router.get(
    "/topics/{topic_id}/research",
    response_model=TopicResearch,
    responses={
        404: {
            "model": TopicNotFoundBody,
            "description": "Unknown topic id, or the topic has no research",
        },
        **NOT_LOADED,
    },
    tags=["Teaching"],
    summary="Trimmed teaching research",
)
def get_research(topic_id: str, service: Service) -> TopicResearch:
    return service.get_research(topic_id)


@router.get(
    "/meta/source",
    response_model=SourceInfo,
    tags=["Meta"],
    summary="Dataset version and attribution",
)
def get_source(service: Service) -> SourceInfo:
    return service.get_source()

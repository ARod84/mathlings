"""Every taxonomy query, for Python callers. No FastAPI in here.

    with Session(engine) as session:
        service = TaxonomyService(session)
        patterns = service.get_error_patterns("mt_...")

Methods take plain arguments and return the Pydantic models in schemas.py.
An unknown topic raises TopicNotFound; the HTTP layer turns that into a 404.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ColumnElement, func
from sqlmodel import Session, col, select

from app.models import ErrorPattern, Prerequisite, TaxonomySource, TeachingResearch, Topic
from app.taxonomy.graph import Edge, Link, PrerequisiteGraph, taxonomy_graph
from app.taxonomy.prompts import render_assessment_prompt
from app.taxonomy.schemas import (
    Depth,
    DomainCount,
    ErrorPatternOut,
    PrerequisiteItem,
    ResearchActivity,
    SourceInfo,
    Strength,
    TopicDetail,
    TopicPage,
    TopicResearch,
    TopicSummary,
    TopicType,
    UnlockItem,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class TaxonomyLookupError(Exception):
    """Base for the errors a caller is expected to handle."""


class TopicNotFound(TaxonomyLookupError):
    def __init__(self, topic_id: str) -> None:
        super().__init__(f"Topic not found: {topic_id}")
        self.topic_id = topic_id


class ResearchNotFound(TaxonomyLookupError):
    def __init__(self, topic_id: str) -> None:
        super().__init__(f"Topic has no research: {topic_id}")
        self.topic_id = topic_id


class TaxonomyNotLoaded(TaxonomyLookupError):
    """The database has not been migrated or imported yet."""


def _source_stamp(session: Session) -> object:
    """Changes whenever an import changes the data (imported_at only moves then)."""
    row = session.exec(select(TaxonomySource.commit_sha, TaxonomySource.imported_at)).first()
    return tuple(row) if row else None


def reload_graph(session: Session, graph: PrerequisiteGraph = taxonomy_graph) -> PrerequisiteGraph:
    """Fill the in-memory graph from the database. Three queries."""
    stamp = _source_stamp(session)
    centrality = dict(session.exec(select(Topic.id, Topic.centrality)).all())
    edges = [
        Edge(*row)
        for row in session.exec(
            select(
                Prerequisite.topic_id,
                Prerequisite.prerequisite_id,
                Prerequisite.strength,
                Prerequisite.reason,
            )
        ).all()
    ]
    graph.reload(edges, centrality, version=stamp)
    return graph


def ensure_graph_fresh(session: Session, graph: PrerequisiteGraph = taxonomy_graph) -> None:
    """Reload the graph if the database was re-imported since it was loaded. One query.

    The importer usually runs in its own process, so the running API cannot be
    told directly; it checks the source row instead.
    """
    if not graph.loaded or graph.version != _source_stamp(session):
        reload_graph(session, graph)


# Topic columns for a summary, plus whether the topic has research, in one query.
_HAS_RESEARCH = col(TeachingResearch.id).is_not(None).label("has_research")
_SUMMARY_COLUMNS = (
    Topic.id,
    Topic.name,
    Topic.subject,
    Topic.domain,
    Topic.type,
    Topic.age_range_start,
    Topic.age_range_end,
    Topic.in_scope,
    _HAS_RESEARCH,
)


def _summary_query():
    return select(*_SUMMARY_COLUMNS).join(
        TeachingResearch, col(TeachingResearch.topic_id) == col(Topic.id), isouter=True
    )


def _to_summary(row: Any) -> TopicSummary:
    return TopicSummary(
        id=row.id,
        name=row.name,
        subject=row.subject,
        domain=row.domain,
        type=row.type,
        age_range_start=row.age_range_start,
        age_range_end=row.age_range_end,
        in_scope=row.in_scope,
        has_research=bool(row.has_research),
    )


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


class TaxonomyService:
    def __init__(self, session: Session, graph: PrerequisiteGraph = taxonomy_graph) -> None:
        self.session = session
        self.graph = graph

    # ---- lists ----

    def list_domains(self, in_scope: bool | None = True) -> list[DomainCount]:
        """Domains with their topic counts. in_scope=None counts every imported topic."""
        query = select(Topic.subject, Topic.domain, func.count()).group_by(
            Topic.subject, Topic.domain
        )
        if in_scope is not None:
            query = query.where(col(Topic.in_scope) == in_scope)
        rows = self.session.exec(query.order_by(Topic.subject, Topic.domain)).all()
        return [DomainCount(subject=s, domain=d, topic_count=n) for s, d, n in rows]

    def list_topics(
        self,
        *,
        domain: str | None = None,
        in_scope: bool | None = True,
        age: int | None = None,
        type: TopicType | None = None,
        q: str | None = None,
        has_research: bool | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> TopicPage:
        """One page of topic summaries, ordered by name. Two queries: the count and the page."""
        limit = max(1, min(limit, MAX_LIMIT))
        offset = max(0, offset)

        filters: list[ColumnElement[bool]] = []
        if domain is not None:
            filters.append(col(Topic.domain) == domain)
        if in_scope is not None:
            filters.append(col(Topic.in_scope) == in_scope)
        if age is not None:
            filters.append(col(Topic.age_range_start) <= age)
            filters.append(col(Topic.age_range_end) >= age)
        if type is not None:
            filters.append(col(Topic.type) == type)
        if q is not None and q.strip():
            pattern = _like_pattern(q.strip())
            filters.append(
                func.lower(Topic.name).like(pattern, escape="\\")
                | func.lower(Topic.description).like(pattern, escape="\\")
            )
        if has_research is not None:
            research_id = col(TeachingResearch.id)
            filters.append(research_id.is_not(None) if has_research else research_id.is_(None))

        total = self.session.exec(
            select(func.count())
            .select_from(Topic)
            .join(TeachingResearch, col(TeachingResearch.topic_id) == col(Topic.id), isouter=True)
            .where(*filters)
        ).one()
        rows = self.session.exec(
            _summary_query()
            .where(*filters)
            .order_by(Topic.name, Topic.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return TopicPage(
            items=[_to_summary(row) for row in rows], total=total, limit=limit, offset=offset
        )

    # ---- one topic ----

    def get_topic(self, topic_id: str, name: str | None = None) -> TopicDetail:
        """The full topic. `name` is the child's name for the assessment prompt."""
        row = self.session.exec(
            select(Topic, _HAS_RESEARCH)
            .join(TeachingResearch, col(TeachingResearch.topic_id) == col(Topic.id), isouter=True)
            .where(col(Topic.id) == topic_id)
        ).first()
        if row is None:
            raise TopicNotFound(topic_id)
        topic, has_research = row
        return TopicDetail(
            id=topic.id,
            name=topic.name,
            subject=topic.subject,
            domain=topic.domain,
            type=topic.type,
            age_range_start=topic.age_range_start,
            age_range_end=topic.age_range_end,
            in_scope=topic.in_scope,
            has_research=bool(has_research),
            description=topic.description,
            evidence=list(topic.evidence),
            centrality=topic.centrality,
            assessment_prompt=render_assessment_prompt(topic.assessment_prompt_template, name),
        )

    def get_prerequisites(
        self, topic_id: str, depth: Depth = "direct", strength: Strength | None = None
    ) -> list[PrerequisiteItem]:
        """What the topic needs first. depth="all" follows the chain back, nearest first."""
        self._require(topic_id)
        links = (
            self.graph.all_prerequisites(topic_id, strength)
            if depth == "all"
            else self.graph.direct_prerequisites(topic_id, strength)
        )
        return self._prerequisite_items(links)

    def get_unlocks(self, topic_id: str) -> list[UnlockItem]:
        """The topics that directly depend on this one."""
        self._require(topic_id)
        links = self.graph.direct_unlocks(topic_id)
        summaries = self._summaries(link.topic_id for link in links)
        return [
            UnlockItem(topic=summaries[link.topic_id], strength=link.strength, reason=link.reason)
            for link in links
            if link.topic_id in summaries
        ]

    def get_step_back(self, topic_id: str) -> list[PrerequisiteItem]:
        """Where to step back to when a child is stuck, best candidate first."""
        self._require(topic_id)
        return self._prerequisite_items(self.graph.step_back_candidates(topic_id))

    def get_error_patterns(self, topic_id: str) -> list[ErrorPatternOut]:
        """The typical mistakes for a topic, in upstream order. Two queries."""
        self._require(topic_id)
        patterns = self.session.exec(
            select(ErrorPattern)
            .where(col(ErrorPattern.topic_id) == topic_id)
            .order_by(ErrorPattern.position)
        ).all()
        summaries = self._summaries(
            p.reteach_prerequisite_id for p in patterns if p.reteach_prerequisite_id
        )
        return [
            ErrorPatternOut(
                id=p.id,
                position=p.position,
                kind=p.kind,
                pattern=p.pattern,
                next_move=p.next_move,
                distractor=p.distractor,
                revealed_by=p.revealed_by,
                reteach_prerequisite=summaries.get(p.reteach_prerequisite_id or ""),
            )
            for p in patterns
        ]

    def get_research(self, topic_id: str) -> TopicResearch:
        """A trimmed view of the teaching research. Raises ResearchNotFound if there is none.

        Only the fields games and hints need are returned: sources, source
        claims, rationales, review notes and the assessment are left out.
        """
        self._require(topic_id)
        research = self.session.exec(
            select(TeachingResearch).where(col(TeachingResearch.topic_id) == topic_id)
        ).first()
        if research is None:
            raise ResearchNotFound(topic_id)
        learn, pedagogy = research.learn or {}, research.pedagogy or {}
        return TopicResearch(
            topic_id=topic_id,
            summary=learn.get("summary", ""),
            activities=[
                ResearchActivity(
                    title=activity.get("title", ""),
                    learner_actions=list(activity.get("learnerActions") or []),
                    intended_insight=activity.get("intendedInsight", ""),
                    feedback=list(activity.get("feedback") or []),
                )
                for activity in learn.get("activities") or []
                if isinstance(activity, dict)
            ],
            common_misconceptions=list(pedagogy.get("commonMisconceptions") or []),
            key_representations=list(pedagogy.get("keyRepresentations") or []),
            confidence=research.confidence,
        )

    def get_source(self) -> SourceInfo:
        source = self.session.exec(select(TaxonomySource)).first()
        if source is None:
            raise TaxonomyNotLoaded("No taxonomy has been imported yet.")
        return SourceInfo(
            commit_sha=source.commit_sha,
            taxonomy_version=source.taxonomy_version,
            imported_at=source.imported_at,
            attribution=source.attribution,
        )

    # ---- helpers ----

    def _require(self, topic_id: str) -> None:
        """Existence check against the in-memory graph, so it costs no query."""
        if topic_id not in self.graph:
            raise TopicNotFound(topic_id)

    def _summaries(self, topic_ids: Iterable[str]) -> dict[str, TopicSummary]:
        """Summaries for any number of topics in one query."""
        wanted = list(dict.fromkeys(topic_ids))
        if not wanted:
            return {}
        rows = self.session.exec(_summary_query().where(col(Topic.id).in_(wanted))).all()
        return {row.id: _to_summary(row) for row in rows}

    def _prerequisite_items(self, links: Sequence[Link]) -> list[PrerequisiteItem]:
        summaries = self._summaries(link.topic_id for link in links)
        return [
            PrerequisiteItem(
                topic=summaries[link.topic_id],
                strength=link.strength,
                reason=link.reason,
                distance=link.distance,
                required_by=link.via,
            )
            for link in links
            if link.topic_id in summaries
        ]

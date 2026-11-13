"""Connects the puzzle library to the taxonomy service. The only database-aware file here.

Everything else in this package takes a MisconceptionCatalog and small
callables, so it can be tested and reused without a database.
"""

from collections.abc import Callable

from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog, resolve_catalog
from app.taxonomy.service import TaxonomyService


def load_catalog(service: TaxonomyService) -> MisconceptionCatalog:
    """Resolve misconceptions.RULE_PATTERNS against the database. Call once at startup."""
    return resolve_catalog(service.get_error_patterns)


def topic_exists(service: TaxonomyService) -> Callable[[str], bool]:
    """For verify(): is this id a topic in the database? Answered from the in-memory graph."""
    # The graph is kept, not the service: the result outlives the request's session.
    graph = service.graph
    return lambda topic_id: topic_id in graph


def first_step_back(service: TaxonomyService) -> Callable[[str], str | None]:
    """For diagnose(): the best step-back topic for a topic, from the prerequisite graph."""

    graph = service.graph

    def lookup(topic_id: str) -> str | None:
        candidates = graph.step_back_candidates(topic_id)
        return candidates[0].topic_id if candidates else None

    return lookup

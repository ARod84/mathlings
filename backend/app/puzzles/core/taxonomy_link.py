"""The two questions every puzzle type asks the taxonomy, as small callables.

A puzzle library takes these instead of a TaxonomyService, so it can be tested
and reused without a database. Both are answered from the in-memory graph,
which is kept, not the service: the result outlives the request's session.
"""

from collections.abc import Callable

from app.taxonomy.service import TaxonomyService


def topic_exists(service: TaxonomyService) -> Callable[[str], bool]:
    """For a verifier: is this id a topic in the database?"""
    graph = service.graph
    return lambda topic_id: topic_id in graph


def first_step_back(service: TaxonomyService) -> Callable[[str], str | None]:
    """For a diagnoser: the best step-back topic for a topic, from the prerequisite graph."""
    graph = service.graph

    def lookup(topic_id: str) -> str | None:
        candidates = graph.step_back_candidates(topic_id)
        return candidates[0].topic_id if candidates else None

    return lookup

"""Connects the chain library to the taxonomy service. The only database-aware file here.

Everything else in this package takes a MisconceptionCatalog and small
callables, so it can be tested and reused without a database. The two
callables are the shared ones in app/puzzles/core/taxonomy_link.py.
"""

from app.puzzles.core.taxonomy_link import first_step_back, topic_exists
from app.puzzles.types.missing_number.misconceptions import MisconceptionCatalog, resolve_catalog
from app.taxonomy.service import TaxonomyService

__all__ = ["first_step_back", "load_catalog", "topic_exists"]


def load_catalog(service: TaxonomyService) -> MisconceptionCatalog:
    """Resolve misconceptions.RULE_PATTERNS against the database. Call once at startup."""
    return resolve_catalog(service.get_error_patterns)

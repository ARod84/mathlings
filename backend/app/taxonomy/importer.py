"""Loads the pinned os-taxonomy dataset into the database.

    uv run python -m app.taxonomy.importer

Order of work: read and verify the files, decide what is in scope, check the
references and the graph, then write everything in one transaction. Nothing is
written if a checksum is wrong or the prerequisite graph has a cycle.
"""

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, inspect
from sqlmodel import Session, SQLModel, select

from app.config import get_settings
from app.db import make_engine
from app.models import (
    Cluster,
    ErrorPattern,
    Prerequisite,
    TaxonomySource,
    TeachingResearch,
    Topic,
)
from app.taxonomy.constants import (
    ATTRIBUTION,
    REVIEWED_COUNTS,
    SCOPE_AGE_MAX,
    SCOPE_AGE_MIN,
    SCOPE_SUBJECT,
    TAXONOMY_COMMIT,
)
from app.taxonomy.service import reload_graph
from app.taxonomy.source import (
    CycleError,
    TaxonomyError,
    TaxonomySourceData,
    load_source,
    read_checkout_commit,
)

logger = logging.getLogger(__name__)

Rows = dict[Any, dict[str, Any]]


@dataclass
class TableDiff:
    added: int = 0
    changed: int = 0
    removed: int = 0

    @property
    def total(self) -> int:
        return self.added + self.changed + self.removed


@dataclass
class ImportPlan:
    """Everything that should be in the database, keyed the way each table is matched."""

    topics: Rows
    prerequisites: Rows
    research: Rows
    error_patterns: Rows
    clusters: Rows
    dangling: list[str]
    closure_non_math: int
    in_scope_without_research: int


@dataclass
class ImportSummary:
    commit_sha: str
    previous_commit_sha: str | None
    topics_in_scope: int
    topics_closure: int
    closure_non_math: int
    edges: int
    research_records: int
    error_patterns: int
    clusters: int
    in_scope_without_research: int
    dangling_references: list[str]
    diffs: dict[str, TableDiff] = field(default_factory=dict)

    @property
    def topics_total(self) -> int:
        return self.topics_in_scope + self.topics_closure

    @property
    def changed_anything(self) -> bool:
        return any(diff.total for diff in self.diffs.values())

    def format(self) -> str:
        def reviewed(key: str, actual: int) -> str:
            expected = REVIEWED_COUNTS[key]
            verdict = "matches" if actual == expected else "DIFFERS"
            return f"{actual:>6}   (reviewed: {expected}, {verdict})"

        lines = [
            "Taxonomy import summary",
            f"  commit                      {self.commit_sha}",
        ]
        if self.previous_commit_sha and self.previous_commit_sha != self.commit_sha:
            lines.append(f"  previous commit             {self.previous_commit_sha}")
        lines += [
            f"  topics, in scope            {reviewed('topics_in_scope', self.topics_in_scope)}",
            f"  topics, closure only        {self.topics_closure:>6}",
            f"    of which not mathematics  {reviewed('closure_non_math', self.closure_non_math)}",
            f"  topics, total               {reviewed('topics_total', self.topics_total)}",
            f"  prerequisite edges          {self.edges:>6}",
            f"  research records            {self.research_records:>6}",
            f"  error patterns              {self.error_patterns:>6}",
            f"  clusters                    {self.clusters:>6}",
            f"  in-scope topics, no research{self.in_scope_without_research:>6}",
            f"  dangling references skipped {len(self.dangling_references):>6}",
            "Changes to the database (added / changed / removed)",
        ]
        for table, diff in self.diffs.items():
            lines.append(f"  {table:<28}{diff.added:>6} /{diff.changed:>6} /{diff.removed:>6}")
        if not self.changed_anything:
            lines.append("  Nothing changed: the database already matched the source.")
        return "\n".join(lines)


def _in_scope(topic: dict[str, Any]) -> bool:
    return (
        topic["subject"] == SCOPE_SUBJECT
        and topic["ageRangeEnd"] >= SCOPE_AGE_MIN
        and topic["ageRangeStart"] <= SCOPE_AGE_MAX
    )


def find_cycle(edges: list[tuple[str, str]]) -> list[str] | None:
    """A cycle in the graph as a list of ids (first id repeated at the end), or None."""
    graph: dict[str, list[str]] = defaultdict(list)
    for topic_id, prerequisite_id in edges:
        graph[topic_id].append(prerequisite_id)

    done: set[str] = set()
    for start in list(graph):
        if start in done:
            continue
        path: list[str] = [start]
        on_path = {start}
        iterators = [iter(graph[start])]
        while iterators:
            for nxt in iterators[-1]:
                if nxt in on_path:
                    return [*path[path.index(nxt) :], nxt]
                if nxt not in done:
                    path.append(nxt)
                    on_path.add(nxt)
                    iterators.append(iter(graph.get(nxt, ())))
                    break
            else:
                finished = path.pop()
                on_path.discard(finished)
                done.add(finished)
                iterators.pop()
    return None


def build_plan(source: TaxonomySourceData) -> ImportPlan:
    """Work out the rows to import. Raises CycleError; logs and skips dangling references."""
    by_id = {topic["id"]: topic for topic in source.topics}
    dangling: list[str] = []

    def note_dangling(message: str) -> None:
        dangling.append(message)
        logger.warning("Dangling reference skipped: %s", message)

    # Edges whose two ends both exist. The rest are reported and dropped.
    valid_edges = []
    for edge in source.dependencies:
        missing = [end for end in (edge["topicId"], edge["prerequisiteId"]) if end not in by_id]
        if missing:
            note_dangling(
                f"dependency {edge['topicId']} -> {edge['prerequisiteId']}: "
                f"unknown topic {', '.join(missing)}"
            )
        else:
            valid_edges.append(edge)

    prerequisites_of: dict[str, list[str]] = defaultdict(list)
    for edge in valid_edges:
        prerequisites_of[edge["topicId"]].append(edge["prerequisiteId"])

    # In-scope topics, plus everything they need, however far back.
    in_scope = {topic_id for topic_id, topic in by_id.items() if _in_scope(topic)}
    imported = set(in_scope)
    stack = list(in_scope)
    while stack:
        for prerequisite_id in prerequisites_of[stack.pop()]:
            if prerequisite_id not in imported:
                imported.add(prerequisite_id)
                stack.append(prerequisite_id)

    topics: Rows = {
        topic_id: {
            "type": by_id[topic_id]["type"],
            "subject": by_id[topic_id]["subject"],
            "domain": by_id[topic_id]["domain"],
            "name": by_id[topic_id]["name"],
            "description": by_id[topic_id]["description"],
            "evidence": list(by_id[topic_id]["evidence"]),
            "assessment_prompt_template": by_id[topic_id]["assessmentPrompt"],
            "age_range_start": by_id[topic_id]["ageRangeStart"],
            "age_range_end": by_id[topic_id]["ageRangeEnd"],
            "centrality": by_id[topic_id]["centrality"],
            "in_scope": topic_id in in_scope,
        }
        for topic_id in sorted(imported)
    }

    # An imported topic's prerequisites are all imported (that is the closure),
    # so filtering on topicId alone keeps the graph complete.
    prerequisites: Rows = {
        (edge["topicId"], edge["prerequisiteId"]): {
            "strength": edge["strength"],
            "reason": edge["reason"],
        }
        for edge in valid_edges
        if edge["topicId"] in imported
    }
    cycle = find_cycle(list(prerequisites))
    if cycle:
        raise CycleError("The prerequisite graph has a cycle: " + " -> ".join(cycle))

    research: Rows = {}
    error_patterns: Rows = {}
    for record in source.research_records:
        topic_id = record["topicId"]
        if topic_id not in by_id:
            note_dangling(f"teaching research for unknown topic {topic_id}")
            continue
        if topic_id not in imported:
            continue
        assess = record.get("assess")
        research[topic_id] = {
            "pedagogy": record["pedagogy"],
            "learn": record["learn"],
            "assess": assess,
            "sources": record["sources"],
            "confidence": record["confidence"],
        }
        for position, pattern in enumerate((assess or {}).get("errorPatterns") or []):
            reteach_id = pattern.get("reteachPrerequisiteId")
            if reteach_id is not None and reteach_id not in imported:
                # The pattern itself is still useful, so only the reference is dropped.
                why = "unknown topic" if reteach_id not in by_id else "topic outside the import"
                note_dangling(
                    f"error pattern {position} of {topic_id}: "
                    f"reteachPrerequisiteId {reteach_id} ({why})"
                )
                reteach_id = None
            error_patterns[(topic_id, position)] = {
                "kind": pattern["kind"],
                "pattern": pattern["pattern"],
                "next_move": pattern["nextMove"],
                "distractor": pattern.get("distractor"),
                "revealed_by": pattern["revealedBy"],
                "reteach_prerequisite_id": reteach_id,
            }

    # A cluster belongs to a subject and domain; keep those that an imported topic is in.
    imported_domains = {(row["subject"], row["domain"]) for row in topics.values()}
    clusters: Rows = {
        (cluster["subject"], cluster["domain"], cluster["ageRangeStart"]): {
            "summary": cluster["summary"]
        }
        for cluster in source.clusters
        if (cluster["subject"], cluster["domain"]) in imported_domains
    }

    return ImportPlan(
        topics=topics,
        prerequisites=prerequisites,
        research=research,
        error_patterns=error_patterns,
        clusters=clusters,
        dangling=dangling,
        closure_non_math=sum(
            1 for row in topics.values() if not row["in_scope"] and row["subject"] != SCOPE_SUBJECT
        ),
        in_scope_without_research=sum(
            1 for topic_id, row in topics.items() if row["in_scope"] and topic_id not in research
        ),
    )


def _sync(
    session: Session,
    model: type[SQLModel],
    key_fields: tuple[str, ...],
    desired: Rows,
    *,
    delete: bool = True,
) -> tuple[TableDiff, list[SQLModel]]:
    """Make a table match `desired`. Returns the diff and the rows that are no longer wanted.

    With delete=False the unwanted rows are returned but left in place, for
    the caller to delete once nothing refers to them.
    """
    single = len(key_fields) == 1

    def key_of(row: SQLModel) -> Any:
        values = tuple(getattr(row, name) for name in key_fields)
        return values[0] if single else values

    existing = {key_of(row): row for row in session.exec(select(model)).all()}
    diff = TableDiff()

    for key, values in desired.items():
        row = existing.get(key)
        if row is None:
            key_values = dict(zip(key_fields, (key,) if single else key, strict=True))
            session.add(model(**key_values, **values))
            diff.added += 1
            continue
        changed = False
        for name, value in values.items():
            if getattr(row, name) != value:
                setattr(row, name, value)
                changed = True
        if changed:
            session.add(row)
            diff.changed += 1

    stale = [row for key, row in existing.items() if key not in desired]
    diff.removed = len(stale)
    if delete:
        for row in stale:
            session.delete(row)
    session.flush()
    return diff, stale


def apply_plan(
    session: Session, plan: ImportPlan, source: TaxonomySourceData, commit_sha: str
) -> ImportSummary:
    """Write the plan into the session's transaction. The caller commits or rolls back."""
    previous = session.get(TaxonomySource, 1)
    previous_commit = previous.commit_sha if previous else None

    diffs: dict[str, TableDiff] = {}
    # Topics first (other tables point at them); topics that are gone are
    # deleted last, once nothing points at them any more.
    diffs["topic"], stale_topics = _sync(session, Topic, ("id",), plan.topics, delete=False)
    diffs["prerequisite"], _ = _sync(
        session, Prerequisite, ("topic_id", "prerequisite_id"), plan.prerequisites
    )
    diffs["teaching_research"], _ = _sync(session, TeachingResearch, ("topic_id",), plan.research)
    diffs["error_pattern"], _ = _sync(
        session, ErrorPattern, ("topic_id", "position"), plan.error_patterns
    )
    diffs["cluster"], _ = _sync(
        session, Cluster, ("subject", "domain", "age_range_start"), plan.clusters
    )
    for topic in stale_topics:
        session.delete(topic)
    session.flush()

    summary = ImportSummary(
        commit_sha=commit_sha,
        previous_commit_sha=previous_commit,
        topics_in_scope=sum(1 for row in plan.topics.values() if row["in_scope"]),
        topics_closure=sum(1 for row in plan.topics.values() if not row["in_scope"]),
        closure_non_math=plan.closure_non_math,
        edges=len(plan.prerequisites),
        research_records=len(plan.research),
        error_patterns=len(plan.error_patterns),
        clusters=len(plan.clusters),
        in_scope_without_research=plan.in_scope_without_research,
        dangling_references=plan.dangling,
        diffs=diffs,
    )

    source_values = {
        "commit_sha": commit_sha,
        "taxonomy_version": source.taxonomy_version,
        "research_schema_version": source.research_schema_version,
        "file_checksums": dict(source.checksums),
        "attribution": ATTRIBUTION,
    }
    if previous is None:
        session.add(TaxonomySource(id=1, imported_at=datetime.now(UTC), **source_values))
    else:
        source_changed = any(getattr(previous, k) != v for k, v in source_values.items())
        if source_changed or summary.changed_anything:
            for name, value in source_values.items():
                setattr(previous, name, value)
            previous.imported_at = datetime.now(UTC)
            session.add(previous)
    session.flush()
    return summary


def run_import(engine: Engine, taxonomy_path: Path, commit_sha: str) -> ImportSummary:
    """Verify, plan and write. One transaction: on any error the database is left as it was."""
    source = load_source(taxonomy_path)
    plan = build_plan(source)
    with Session(engine) as session, session.begin():
        summary = apply_plan(session, plan, source, commit_sha)
    # Refresh the in-memory prerequisite graph for anything in this process
    # that uses it. A running API server is a separate process: it notices the
    # new import by itself (see service.ensure_graph_fresh).
    with Session(engine) as session:
        reload_graph(session)
    return summary


def checked_commit(taxonomy_path: Path) -> str:
    """The vendor checkout's commit, which must be the pinned one."""
    commit = read_checkout_commit(taxonomy_path)
    if commit is None:
        raise TaxonomyError(
            f"{taxonomy_path} is not a git checkout, so its version cannot be confirmed. "
            "Run scripts/fetch_taxonomy first."
        )
    if commit != TAXONOMY_COMMIT:
        raise TaxonomyError(
            f"{taxonomy_path} is at commit {commit}, but the pinned commit is {TAXONOMY_COMMIT}. "
            "Run scripts/fetch_taxonomy to check out the pinned version."
        )
    return commit


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    engine = make_engine()
    if not inspect(engine).has_table(Topic.__tablename__):
        print(
            f"The database at {settings.database_path} has no tables yet. "
            "Run `uv run alembic upgrade head` first.",
            file=sys.stderr,
        )
        return 1
    try:
        commit = checked_commit(settings.taxonomy_path)
        summary = run_import(engine, settings.taxonomy_path, commit)
    except TaxonomyError as error:
        print(f"IMPORT FAILED, nothing was written: {error}", file=sys.stderr)
        return 1
    print(summary.format())
    return 0


if __name__ == "__main__":
    sys.exit(main())

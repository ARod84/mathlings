import logging
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.models import (
    Cluster,
    ErrorPattern,
    Prerequisite,
    TaxonomySource,
    TeachingResearch,
    Topic,
)
from app.taxonomy.constants import ATTRIBUTION
from app.taxonomy.importer import checked_commit, find_cycle, run_import
from app.taxonomy.source import ChecksumError, CycleError, TaxonomyError
from tests.conftest import FIXTURE_COMMIT

TABLES = (
    "taxonomy_source",
    "topic",
    "prerequisite",
    "teaching_research",
    "error_pattern",
    "cluster",
)


def dump(engine: Engine) -> dict[str, list[tuple]]:
    """Every row of every taxonomy table, for comparing two states of the database."""
    with engine.connect() as connection:
        return {
            table: [
                tuple(row) for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY 1"))
            ]
            for table in TABLES
        }


def test_scope_filtering_and_prerequisite_closure(engine: Engine, taxonomy: Path):
    summary = run_import(engine, taxonomy, FIXTURE_COMMIT)

    with Session(engine) as session:
        topics = {topic.id: topic for topic in session.exec(select(Topic)).all()}

    # In scope: mathematics, age range overlapping 7-12.
    assert {id_ for id_, topic in topics.items() if topic.in_scope} == {
        "mt_add2",
        "mt_placevalue",
        "mt_frac",
    }
    # Closure: reached through prerequisites, one of them two steps away and not mathematics.
    assert {id_ for id_, topic in topics.items() if not topic.in_scope} == {"mt_count", "mt_words"}
    assert topics["mt_words"].subject == "English"
    # Too old with nothing depending on it, and an unrelated subject: left out.
    assert "mt_algebra" not in topics
    assert "mt_forces" not in topics

    assert summary.topics_in_scope == 3
    assert summary.topics_closure == 2
    assert summary.closure_non_math == 1
    assert summary.topics_total == 5
    assert summary.in_scope_without_research == 1  # mt_frac
    assert summary.dangling_references == []


def test_topic_fields_are_stored_as_given(engine: Engine, taxonomy: Path):
    run_import(engine, taxonomy, FIXTURE_COMMIT)

    with Session(engine) as session:
        topic = session.get(Topic, "mt_add2")
        frac = session.get(Topic, "mt_frac")

    assert topic.type == "PROCEDURAL"
    assert topic.domain == "Number"
    assert topic.name == "Two-digit addition"
    assert topic.evidence == ["Shows two-digit addition once", "Explains two-digit addition"]
    assert "{{name}}" in topic.assessment_prompt_template
    assert (topic.age_range_start, topic.age_range_end) == (7, 9)
    assert topic.centrality == pytest.approx(0.1)
    assert frac.centrality is None


def test_standards_are_never_imported(engine: Engine, taxonomy: Path):
    run_import(engine, taxonomy, FIXTURE_COMMIT)

    with engine.connect() as connection:
        columns = [row[1] for row in connection.execute(text("PRAGMA table_info(topic)"))]
        stored = str(dump(engine))
    assert "standards" not in columns
    assert "fixture-curriculum" not in stored


def test_edges_research_and_clusters_follow_the_imported_topics(engine: Engine, taxonomy: Path):
    summary = run_import(engine, taxonomy, FIXTURE_COMMIT)

    with Session(engine) as session:
        edges = {
            (edge.topic_id, edge.prerequisite_id): edge
            for edge in session.exec(select(Prerequisite)).all()
        }
        research = {row.topic_id: row for row in session.exec(select(TeachingResearch)).all()}
        clusters = {(c.subject, c.domain) for c in session.exec(select(Cluster)).all()}

    # mt_algebra -> mt_add2 is dropped: mt_algebra is not imported.
    assert set(edges) == {
        ("mt_add2", "mt_placevalue"),
        ("mt_placevalue", "mt_count"),
        ("mt_count", "mt_words"),
        ("mt_frac", "mt_add2"),
    }
    assert edges[("mt_count", "mt_words")].strength == "soft"
    assert edges[("mt_add2", "mt_placevalue")].reason == "mt_add2 builds on mt_placevalue."

    assert set(research) == {"mt_add2", "mt_placevalue"}
    assert research["mt_add2"].pedagogy["bestPractices"] == ["Use concrete materials first"]
    assert research["mt_add2"].learn["schemaVersion"] == 1
    assert research["mt_add2"].assess["correctAnswer"] == "71"
    assert research["mt_add2"].sources[0]["title"] == "Fixture source"
    assert research["mt_add2"].confidence == "high"
    assert research["mt_placevalue"].assess is None

    assert clusters == {("Mathematics", "Number"), ("English", "Vocabulary")}
    assert (summary.edges, summary.research_records, summary.clusters) == (4, 2, 2)


def test_error_patterns_are_normalized(engine: Engine, taxonomy: Path):
    summary = run_import(engine, taxonomy, FIXTURE_COMMIT)

    with Session(engine) as session:
        patterns = session.exec(select(ErrorPattern).order_by(ErrorPattern.position)).all()

    assert summary.error_patterns == 3
    assert [p.topic_id for p in patterns] == ["mt_add2"] * 3
    assert [p.position for p in patterns] == [0, 1, 2]
    assert [p.kind for p in patterns] == ["misconception", "performance", "developmental"]

    first, second, third = patterns
    assert first.pattern.startswith("Adds each column separately")
    assert first.next_move.startswith("Build both numbers")
    assert first.distractor == "611"
    assert first.revealed_by == "Writes 611"
    assert first.reteach_prerequisite_id == "mt_placevalue"
    assert second.distractor == "61"
    assert second.reteach_prerequisite_id is None
    assert third.distractor is None
    # A reteach target that is in the import only through the closure still resolves.
    assert third.reteach_prerequisite_id == "mt_count"


def test_source_row_records_version_checksums_and_attribution(engine: Engine, taxonomy: Path):
    run_import(engine, taxonomy, FIXTURE_COMMIT)

    with Session(engine) as session:
        rows = session.exec(select(TaxonomySource)).all()

    assert len(rows) == 1
    source = rows[0]
    assert source.commit_sha == FIXTURE_COMMIT
    assert source.taxonomy_version == "fixture-v1"
    assert source.research_schema_version == 1
    assert source.attribution == ATTRIBUTION
    assert set(source.file_checksums) == {
        "topics.json",
        "dependencies.json",
        "teaching-research.json",
        "clusters.json",
    }
    assert all(len(value) == 64 for value in source.file_checksums.values())
    assert source.imported_at is not None


def test_checksum_mismatch_aborts_and_writes_nothing(engine: Engine, taxonomy: Path, edit_taxonomy):
    edit_taxonomy("dependencies.json", lambda data: data["dependencies"].pop(), fix_checksums=False)

    with pytest.raises(ChecksumError, match=r"dependencies\.json"):
        run_import(engine, taxonomy, FIXTURE_COMMIT)
    assert all(rows == [] for rows in dump(engine).values())


def test_research_exported_for_other_topics_file_aborts(
    engine: Engine, taxonomy: Path, edit_taxonomy
):
    # Every file matches the manifest, but the research names a different topics.json.
    edit_taxonomy("teaching-research.json", lambda data: data.update(topicFileSha256="0" * 64))

    with pytest.raises(ChecksumError, match="topicFileSha256"):
        run_import(engine, taxonomy, FIXTURE_COMMIT)
    assert all(rows == [] for rows in dump(engine).values())


def test_cycle_aborts_and_leaves_previous_data_intact(
    engine: Engine, taxonomy: Path, edit_taxonomy
):
    run_import(engine, taxonomy, FIXTURE_COMMIT)
    before = dump(engine)

    # mt_add2 -> mt_placevalue -> mt_count -> mt_add2
    edit_taxonomy(
        "dependencies.json",
        lambda data: data["dependencies"].append(
            {"topicId": "mt_count", "prerequisiteId": "mt_add2", "strength": "hard", "reason": "x"}
        ),
    )

    with pytest.raises(CycleError, match="mt_add2"):
        run_import(engine, taxonomy, "e" * 40)
    assert dump(engine) == before


def test_failure_while_writing_rolls_everything_back(
    engine: Engine, taxonomy: Path, edit_taxonomy, monkeypatch: pytest.MonkeyPatch
):
    run_import(engine, taxonomy, FIXTURE_COMMIT)
    before = dump(engine)

    edit_taxonomy("topics.json", lambda data: data["topics"][0].update(name="Renamed"))
    import app.taxonomy.importer as importer

    real_sync = importer._sync

    def failing_sync(session, model, *args, **kwargs):
        if model is Cluster:
            raise RuntimeError("disk full")
        return real_sync(session, model, *args, **kwargs)

    monkeypatch.setattr(importer, "_sync", failing_sync)

    with pytest.raises(RuntimeError, match="disk full"):
        run_import(engine, taxonomy, FIXTURE_COMMIT)
    assert dump(engine) == before


def test_dangling_references_are_skipped_and_logged(
    engine: Engine, taxonomy: Path, edit_taxonomy, caplog: pytest.LogCaptureFixture
):
    edit_taxonomy(
        "dependencies.json",
        lambda data: data["dependencies"].append(
            {
                "topicId": "mt_add2",
                "prerequisiteId": "mt_missing",
                "strength": "hard",
                "reason": "x",
            }
        ),
    )

    def break_research(data):
        patterns = data["records"][0]["assess"]["errorPatterns"]
        patterns[0]["reteachPrerequisiteId"] = "mt_ghost"
        data["records"].append({**data["records"][0], "topicId": "mt_nowhere"})

    edit_taxonomy("teaching-research.json", break_research)

    with caplog.at_level(logging.WARNING, logger="app.taxonomy.importer"):
        summary = run_import(engine, taxonomy, FIXTURE_COMMIT)

    assert len(summary.dangling_references) == 3
    logged = " | ".join(record.getMessage() for record in caplog.records)
    assert "mt_missing" in logged
    assert "mt_ghost" in logged
    assert "mt_nowhere" in logged

    with Session(engine) as session:
        edges = {(e.topic_id, e.prerequisite_id) for e in session.exec(select(Prerequisite)).all()}
        patterns = session.exec(select(ErrorPattern).order_by(ErrorPattern.position)).all()
        topics = {t.id for t in session.exec(select(Topic)).all()}

    # The bad edge is gone, the good ones stay, and no phantom topic appears.
    assert ("mt_add2", "mt_missing") not in edges
    assert len(edges) == 4
    assert topics == {"mt_add2", "mt_placevalue", "mt_frac", "mt_count", "mt_words"}
    # The pattern is kept; only its broken reference is dropped.
    assert len(patterns) == 3
    assert patterns[0].distractor == "611"
    assert patterns[0].reteach_prerequisite_id is None


def test_rerun_is_idempotent(engine: Engine, taxonomy: Path):
    first = run_import(engine, taxonomy, FIXTURE_COMMIT)
    before = dump(engine)

    second = run_import(engine, taxonomy, FIXTURE_COMMIT)

    # Identical rows, ids and timestamp included: nothing duplicated, nothing rewritten.
    assert dump(engine) == before
    assert first.changed_anything
    assert not second.changed_anything
    assert all(diff.total == 0 for diff in second.diffs.values())
    assert second.topics_total == first.topics_total == 5


def test_new_version_updates_rows_and_reports_the_difference(
    engine: Engine, taxonomy: Path, edit_taxonomy
):
    run_import(engine, taxonomy, FIXTURE_COMMIT)
    with Session(engine) as session:
        kept_id = session.exec(select(ErrorPattern.id).where(ErrorPattern.position == 0)).one()

    def change_topics(data):
        topics = {topic["id"]: topic for topic in data["topics"]}
        topics["mt_add2"]["name"] = "Adding two-digit numbers"  # changed
        topics["mt_frac"]["ageRangeStart"] = 13  # now out of scope -> removed
        topics["mt_frac"]["ageRangeEnd"] = 14
        topics["mt_algebra"]["ageRangeStart"] = 12  # now in scope -> added

    edit_taxonomy("topics.json", change_topics)
    edit_taxonomy(
        "teaching-research.json",
        lambda data: data["records"][0]["assess"]["errorPatterns"].pop(),
    )

    new_commit = "a" * 40
    summary = run_import(engine, taxonomy, new_commit)

    assert summary.previous_commit_sha == FIXTURE_COMMIT
    assert summary.commit_sha == new_commit
    topic_diff = summary.diffs["topic"]
    assert (topic_diff.added, topic_diff.changed, topic_diff.removed) == (1, 1, 1)
    # mt_frac -> mt_add2 goes, mt_algebra -> mt_add2 arrives.
    edge_diff = summary.diffs["prerequisite"]
    assert (edge_diff.added, edge_diff.removed) == (1, 1)
    assert summary.diffs["error_pattern"].removed == 1
    assert summary.diffs["teaching_research"].changed == 1

    with Session(engine) as session:
        topics = {t.id: t for t in session.exec(select(Topic)).all()}
        source = session.exec(select(TaxonomySource)).one()
        patterns = session.exec(select(ErrorPattern)).all()

    assert topics["mt_add2"].name == "Adding two-digit numbers"
    assert "mt_frac" not in topics
    assert topics["mt_algebra"].in_scope
    assert source.commit_sha == new_commit
    assert len(patterns) == 2
    # Rows that survive keep their ids, so anything pointing at them stays valid.
    assert kept_id in {p.id for p in patterns}


def test_summary_text_compares_counts_with_the_reviewed_ones(engine: Engine, taxonomy: Path):
    text_ = run_import(engine, taxonomy, FIXTURE_COMMIT).format()

    assert "topics, in scope" in text_
    assert "reviewed: 561, DIFFERS" in text_  # the fixture is not the real dataset
    assert "in-scope topics, no research" in text_


def test_find_cycle():
    assert find_cycle([("a", "b"), ("b", "c"), ("a", "c")]) is None
    assert find_cycle([]) is None
    cycle = find_cycle([("a", "b"), ("b", "c"), ("c", "a"), ("x", "a")])
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b", "c"}
    assert find_cycle([("a", "a")]) == ["a", "a"]


def test_missing_taxonomy_fails_with_a_clear_message(engine: Engine, tmp_path: Path):
    with pytest.raises(TaxonomyError, match="fetch_taxonomy"):
        run_import(engine, tmp_path / "nowhere", FIXTURE_COMMIT)


def test_checkout_must_be_at_the_pinned_commit(tmp_path: Path):
    from app.taxonomy.constants import TAXONOMY_COMMIT

    with pytest.raises(TaxonomyError, match="not a git checkout"):
        checked_commit(tmp_path)

    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("b" * 40 + "\n", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="pinned commit"):
        checked_commit(tmp_path)

    (tmp_path / ".git" / "HEAD").write_text(TAXONOMY_COMMIT + "\n", encoding="utf-8")
    assert checked_commit(tmp_path) == TAXONOMY_COMMIT

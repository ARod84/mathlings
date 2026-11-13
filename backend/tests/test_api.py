import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session

from app.config import BACKEND_DIR, Settings
from app.main import create_app
from app.taxonomy.constants import ATTRIBUTION
from app.taxonomy.graph import PrerequisiteGraph, taxonomy_graph
from app.taxonomy.importer import run_import
from app.taxonomy.schemas import RESEARCH_NOTE
from app.taxonomy.service import TaxonomyService, TopicNotFound
from tests.conftest import FIXTURE_COMMIT, FIXTURE_TAXONOMY, migrate

API = "/api/v1"


@contextmanager
def api_client(database_path: Path, **settings) -> Iterator[TestClient]:
    """A running app (lifespan included) on the given database, with its own graph."""
    app = create_app(
        Settings(_env_file=None, database_path=database_path, **settings),
        graph=PrerequisiteGraph(),
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The fixture taxonomy, imported once per test session into a temporary database."""
    database_path = tmp_path_factory.mktemp("api") / "api.db"
    engine = migrate(database_path)
    run_import(engine, FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()
    with api_client(database_path) as test_client:
        yield test_client


@contextmanager
def count_statements(client: TestClient) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def get(client: TestClient, path: str, **params):
    response = client.get(f"{API}{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def names(payload) -> list[str]:
    return [item["name"] for item in payload["items"]]


# ---- health, meta, app setup ----


def test_health_reports_the_loaded_taxonomy(client: TestClient):
    assert client.get("/health").json() == {
        "status": "ok",
        "taxonomy_loaded": True,
        "topic_count": 5,
    }


def test_health_and_routes_before_any_import(tmp_path: Path):
    with api_client(tmp_path / "empty.db") as empty:
        assert empty.get("/health").json() == {
            "status": "ok",
            "taxonomy_loaded": False,
            "topic_count": 0,
        }
        response = empty.get(f"{API}/topics")
        assert response.status_code == 503
        assert "importer" in response.json()["detail"]


def test_meta_source(client: TestClient):
    source = get(client, "/meta/source")

    assert source["commit_sha"] == FIXTURE_COMMIT
    assert source["taxonomy_version"] == "fixture-v1"
    assert source["attribution"] == ATTRIBUTION
    assert source["imported_at"]
    assert set(source) == {"commit_sha", "taxonomy_version", "imported_at", "attribution"}


def test_cors_allows_only_the_configured_origin(client: TestClient):
    allowed = client.get(f"{API}/domains", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"

    other = client.get(f"{API}/domains", headers={"Origin": "http://evil.example"})
    assert other.status_code == 200
    assert "access-control-allow-origin" not in other.headers


def test_cors_origin_comes_from_settings(tmp_path: Path):
    with api_client(tmp_path / "x.db", cors_origins=["https://app.example"]) as custom:
        response = custom.get("/health", headers={"Origin": "https://app.example"})
        assert response.headers["access-control-allow-origin"] == "https://app.example"
        default = custom.get("/health", headers={"Origin": "http://localhost:5173"})
        assert "access-control-allow-origin" not in default.headers


def test_every_route_is_get_with_a_tag_and_a_response_model(client: TestClient):
    document = client.get("/openapi.json").json()

    assert len(document["paths"]) == 10
    for path, operations in document["paths"].items():
        assert list(operations) == ["get"], path
        operation = operations["get"]
        assert operation["tags"], path
        assert operation["summary"], path
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema != {}, path


def test_exported_openapi_file_is_up_to_date(client: TestClient):
    exported = BACKEND_DIR.parent / "openapi.json"
    assert exported.is_file(), "run: uv run python scripts/export_openapi.py"
    assert json.loads(exported.read_text(encoding="utf-8")) == client.get("/openapi.json").json(), (
        "openapi.json is stale; run: uv run python scripts/export_openapi.py"
    )


# ---- /domains ----


def test_domains_default_to_in_scope(client: TestClient):
    assert get(client, "/domains") == [
        {"subject": "Mathematics", "domain": "Fractions", "topic_count": 1},
        {"subject": "Mathematics", "domain": "Number", "topic_count": 2},
    ]


def test_domains_of_prerequisite_only_topics(client: TestClient):
    assert get(client, "/domains", in_scope="false") == [
        {"subject": "English", "domain": "Vocabulary", "topic_count": 1},
        {"subject": "Mathematics", "domain": "Number", "topic_count": 1},
    ]


# ---- /topics ----


def test_topics_default_page(client: TestClient):
    page = get(client, "/topics")

    assert names(page) == ["Place value", "Two-digit addition", "Unit fractions"]
    assert (page["total"], page["limit"], page["offset"]) == (3, 50, 0)
    assert page["items"][1] == {
        "id": "mt_add2",
        "name": "Two-digit addition",
        "subject": "Mathematics",
        "domain": "Number",
        "type": "PROCEDURAL",
        "age_range_start": 7,
        "age_range_end": 9,
        "in_scope": True,
        "has_research": True,
    }


def test_topics_pagination_keeps_the_full_total(client: TestClient):
    first = get(client, "/topics", limit=2)
    assert names(first) == ["Place value", "Two-digit addition"]
    assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)

    second = get(client, "/topics", limit=2, offset=2)
    assert names(second) == ["Unit fractions"]
    assert (second["total"], second["limit"], second["offset"]) == (3, 2, 2)

    beyond = get(client, "/topics", offset=10)
    assert beyond["items"] == []
    assert beyond["total"] == 3


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"domain": "Fractions"}, ["Unit fractions"]),
        ({"domain": "Number"}, ["Place value", "Two-digit addition"]),
        ({"domain": "Nope"}, []),
        ({"in_scope": "false"}, ["Counting to twenty", "Number words"]),
        ({"age": 6}, ["Place value"]),
        ({"age": 9}, ["Two-digit addition", "Unit fractions"]),
        ({"age": 12}, []),
        ({"age": 5, "in_scope": "false"}, ["Counting to twenty", "Number words"]),
        ({"type": "CONCEPTUAL"}, ["Place value"]),
        ({"type": "LANGUAGE", "in_scope": "false"}, ["Number words"]),
        ({"q": "FRACTION"}, ["Unit fractions"]),  # name, any case
        ({"q": "description of place"}, ["Place value"]),  # description
        ({"q": "  two-digit "}, ["Two-digit addition"]),
        ({"q": "%"}, []),  # a wildcard character is searched for literally
        ({"q": "zzz"}, []),
        ({"has_research": "true"}, ["Place value", "Two-digit addition"]),
        ({"has_research": "false"}, ["Unit fractions"]),
        ({"domain": "Number", "type": "PROCEDURAL", "age": 8}, ["Two-digit addition"]),
    ],
)
def test_topics_filters(client: TestClient, params, expected):
    page = get(client, "/topics", **params)

    assert names(page) == expected
    assert page["total"] == len(expected)


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 201},
        {"limit": 0},
        {"offset": -1},
        {"type": "BOGUS"},
        {"age": "seven"},
        {"in_scope": "maybe"},
    ],
)
def test_topics_invalid_params_are_422(client: TestClient, params):
    assert client.get(f"{API}/topics", params=params).status_code == 422


def test_topics_max_limit_is_accepted(client: TestClient):
    assert get(client, "/topics", limit=200)["limit"] == 200


# ---- /topics/{id} ----


def test_topic_detail(client: TestClient):
    topic = get(client, "/topics/mt_add2")

    assert topic == {
        "id": "mt_add2",
        "name": "Two-digit addition",
        "subject": "Mathematics",
        "domain": "Number",
        "type": "PROCEDURAL",
        "age_range_start": 7,
        "age_range_end": 9,
        "in_scope": True,
        "has_research": True,
        "description": "Fixture description of Two-digit addition.",
        "evidence": ["Shows two-digit addition once", "Explains two-digit addition"],
        "centrality": pytest.approx(0.1),
        "assessment_prompt": "Can you show two-digit addition and explain how you did it?",
    }


def test_topic_detail_renders_the_name_and_never_the_template(client: TestClient):
    named = get(client, "/topics/mt_add2", name="Mia")
    assert named["assessment_prompt"] == (
        "Can Mia show two-digit addition and explain how they did it?"
    )
    for params in ({}, {"name": "Mia"}, {"name": "  "}):
        body = client.get(f"{API}/topics/mt_add2", params=params).text
        assert "{{" not in body
        assert "assessment_prompt_template" not in body


def test_topic_detail_of_a_topic_without_research_or_centrality(client: TestClient):
    topic = get(client, "/topics/mt_frac")
    assert topic["has_research"] is False
    assert topic["centrality"] is None

    assert get(client, "/topics/mt_words")["in_scope"] is False


@pytest.mark.parametrize(
    "suffix", ["", "/prerequisites", "/unlocks", "/step-back", "/error-patterns", "/research"]
)
def test_unknown_topic_is_404_with_the_id(client: TestClient, suffix):
    # mt_algebra is in the source files but outside the import, so it is unknown too.
    for topic_id in ("mt_nope", "mt_algebra"):
        response = client.get(f"{API}/topics/{topic_id}{suffix}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Topic not found", "topic_id": topic_id}


# ---- prerequisites, unlocks, step-back ----


def test_direct_prerequisites(client: TestClient):
    items = get(client, "/topics/mt_add2/prerequisites")

    assert len(items) == 1
    assert items[0] == {
        "topic": {
            "id": "mt_placevalue",
            "name": "Place value",
            "subject": "Mathematics",
            "domain": "Number",
            "type": "CONCEPTUAL",
            "age_range_start": 6,
            "age_range_end": 8,
            "in_scope": True,
            "has_research": True,
        },
        "strength": "hard",
        "reason": "mt_add2 builds on mt_placevalue.",
        "distance": 1,
        "required_by": "mt_add2",
    }
    assert get(client, "/topics/mt_add2/prerequisites", depth="direct") == items


def test_transitive_prerequisites_have_distances(client: TestClient):
    items = get(client, "/topics/mt_add2/prerequisites", depth="all")

    assert [(i["topic"]["id"], i["distance"], i["strength"], i["required_by"]) for i in items] == [
        ("mt_placevalue", 1, "hard", "mt_add2"),
        ("mt_count", 2, "hard", "mt_placevalue"),
        ("mt_words", 3, "soft", "mt_count"),
    ]
    # The chain leaves the in-scope set, and reaches another subject.
    assert [i["topic"]["in_scope"] for i in items] == [True, False, False]
    assert items[2]["topic"]["subject"] == "English"
    assert items[2]["reason"] == "mt_count builds on mt_words."


def test_prerequisites_strength_filter(client: TestClient):
    def reached(**params):
        return [i["topic"]["id"] for i in get(client, "/topics/mt_add2/prerequisites", **params)]

    assert reached(depth="all", strength="hard") == ["mt_placevalue", "mt_count"]
    assert reached(depth="all", strength="soft") == []
    assert reached(strength="soft") == []
    assert [
        i["topic"]["id"] for i in get(client, "/topics/mt_count/prerequisites", strength="soft")
    ] == ["mt_words"]
    assert get(client, "/topics/mt_words/prerequisites", depth="all") == []


@pytest.mark.parametrize("params", [{"depth": "sideways"}, {"strength": "firm"}])
def test_prerequisites_invalid_params_are_422(client: TestClient, params):
    response = client.get(f"{API}/topics/mt_add2/prerequisites", params=params)
    assert response.status_code == 422


def test_unlocks(client: TestClient):
    unlocks = get(client, "/topics/mt_add2/unlocks")

    # mt_algebra also depends on mt_add2 upstream, but it was not imported.
    assert len(unlocks) == 1
    assert unlocks[0]["topic"]["id"] == "mt_frac"
    assert unlocks[0]["strength"] == "soft"
    assert unlocks[0]["reason"] == "mt_frac builds on mt_add2."
    assert set(unlocks[0]) == {"topic", "strength", "reason"}
    assert get(client, "/topics/mt_frac/unlocks") == []


def test_step_back_on_the_fixture_chain(client: TestClient):
    items = get(client, "/topics/mt_add2/step-back")

    assert [(i["topic"]["id"], i["distance"]) for i in items] == [
        ("mt_placevalue", 1),
        ("mt_count", 2),
        ("mt_words", 3),
    ]
    assert get(client, "/topics/mt_words/step-back") == []


def test_step_back_ordering(tmp_path: Path, edit_taxonomy, taxonomy: Path):
    """Direct hard, then direct soft, then further back; ties go to the more central topic."""

    def set_centrality(data):
        values = {"mt_placevalue": 0.2, "mt_count": 0.9, "mt_words": 0.95, "mt_frac": 0.4}
        for topic in data["topics"]:
            topic["centrality"] = values.get(topic["id"], topic["centrality"])
            if topic["id"] == "mt_algebra":
                topic["ageRangeStart"] = 12  # bring it into scope as the starting point

    def add_edges(data):
        def edge(topic_id, prerequisite_id, strength):
            return {
                "topicId": topic_id,
                "prerequisiteId": prerequisite_id,
                "strength": strength,
                "reason": f"{topic_id} needs {prerequisite_id}",
            }

        # mt_algebra -> mt_add2 (hard) is already there.
        data["dependencies"] += [
            edge("mt_algebra", "mt_words", "soft"),  # direct soft, the most central of all
            edge("mt_algebra", "mt_placevalue", "hard"),  # direct hard, low centrality
            edge("mt_algebra", "mt_frac", "hard"),  # direct hard, higher centrality
        ]

    edit_taxonomy("topics.json", set_centrality)
    edit_taxonomy("dependencies.json", add_edges)
    engine = migrate(tmp_path / "stepback.db")
    run_import(engine, taxonomy, FIXTURE_COMMIT)
    engine.dispose()

    with api_client(tmp_path / "stepback.db") as custom:
        items = get(custom, "/topics/mt_algebra/step-back")

    assert [(i["topic"]["id"], i["distance"], i["strength"]) for i in items] == [
        ("mt_frac", 1, "hard"),  # centrality 0.4
        ("mt_placevalue", 1, "hard"),  # 0.2
        ("mt_add2", 1, "hard"),  # 0.1
        ("mt_words", 1, "soft"),  # 0.95, but soft comes after hard
        ("mt_count", 2, "hard"),
    ]


# ---- error patterns, research ----


def test_error_patterns(client: TestClient):
    patterns = get(client, "/topics/mt_add2/error-patterns")

    assert [p["kind"] for p in patterns] == ["misconception", "performance", "developmental"]
    first, second, third = patterns
    assert set(first) == {
        "id",
        "position",
        "kind",
        "pattern",
        "next_move",
        "distractor",
        "revealed_by",
        "reteach_prerequisite",
    }
    assert first["pattern"].startswith("Adds each column separately")
    assert first["next_move"].startswith("Build both numbers")
    assert first["distractor"] == "611"
    assert first["revealed_by"] == "Writes 611"
    assert first["reteach_prerequisite"] == {
        "id": "mt_placevalue",
        "name": "Place value",
        "subject": "Mathematics",
        "domain": "Number",
        "type": "CONCEPTUAL",
        "age_range_start": 6,
        "age_range_end": 8,
        "in_scope": True,
        "has_research": True,
    }
    assert second["reteach_prerequisite"] is None
    assert second["distractor"] == "61"
    assert third["distractor"] is None
    assert third["reteach_prerequisite"]["id"] == "mt_count"


def test_error_patterns_can_be_empty(client: TestClient):
    assert get(client, "/topics/mt_placevalue/error-patterns") == []
    assert get(client, "/topics/mt_frac/error-patterns") == []


def test_research_is_trimmed(client: TestClient):
    response = client.get(f"{API}/topics/mt_add2/research")
    research = response.json()

    assert research == {
        "topic_id": "mt_add2",
        "summary": "A short activity sequence.",
        "activities": [
            {
                "title": "Build it",
                "learner_actions": ["Make both numbers with blocks", "Trade ten ones for a ten"],
                "intended_insight": "Ten ones are worth one ten.",
                "feedback": ["If the trade is skipped, count the ones together."],
            }
        ],
        "common_misconceptions": ["Digits are added without regard to place"],
        "key_representations": ["Base-ten blocks"],
        "confidence": "high",
        "research_note": RESEARCH_NOTE,
    }
    assert RESEARCH_NOTE == "Agent-authored research; sources not independently verified."
    # Nothing else from the stored record leaks out.
    for leaked in (
        '"sources"',
        "Fixture source",
        "example.org",
        "provenance",
        "sourceClaims",
        "A fixture claim",
        "rationale",
        "bestPractices",
        "Use concrete materials",
        "errorPatterns",
        "correctAnswer",
        "reviewNotes",
        "publicationNotes",
    ):
        assert leaked not in response.text, leaked


def test_research_404_when_the_topic_has_none(client: TestClient):
    response = client.get(f"{API}/topics/mt_frac/research")

    assert response.status_code == 404
    assert response.json() == {"detail": "Topic has no research", "topic_id": "mt_frac"}


# ---- query counts ----


def test_topics_list_uses_a_fixed_number_of_statements(client: TestClient):
    with count_statements(client) as one:
        get(client, "/topics", limit=1)
    with count_statements(client) as many:
        get(client, "/topics", limit=200, in_scope="false", q="o")

    # The freshness check, the count and the page: never one per row.
    assert len(one) == 3, one
    assert len(many) == 3, many


def test_transitive_prerequisites_use_a_fixed_number_of_statements(client: TestClient):
    with count_statements(client) as leaf:
        assert get(client, "/topics/mt_words/prerequisites", depth="all") == []
    with count_statements(client) as chain:
        assert len(get(client, "/topics/mt_add2/prerequisites", depth="all")) == 3

    # The graph walk is in memory: one freshness check, then one query for all summaries.
    assert len(leaf) == 1, leaf
    assert len(chain) == 2, chain


@pytest.mark.parametrize(
    ("path", "maximum"),
    [
        ("/domains", 2),
        ("/topics/mt_add2", 2),
        ("/topics/mt_add2/unlocks", 2),
        ("/topics/mt_add2/step-back", 2),
        ("/topics/mt_add2/error-patterns", 3),
        ("/topics/mt_add2/research", 2),
        ("/meta/source", 2),
    ],
)
def test_every_endpoint_has_a_small_statement_budget(client: TestClient, path, maximum):
    with count_statements(client) as statements:
        get(client, path)
    assert len(statements) <= maximum, statements


# ---- reload, and the service used directly ----


def test_a_reimport_is_picked_up_without_restarting(tmp_path: Path, edit_taxonomy, taxonomy: Path):
    database_path = tmp_path / "reload.db"
    engine = migrate(database_path)
    run_import(engine, taxonomy, FIXTURE_COMMIT)

    with api_client(database_path) as running:
        before = get(running, "/topics/mt_frac/prerequisites")
        assert [i["topic"]["id"] for i in before] == ["mt_add2"]

        edit_taxonomy(
            "dependencies.json",
            lambda data: data["dependencies"].append(
                {
                    "topicId": "mt_frac",
                    "prerequisiteId": "mt_placevalue",
                    "strength": "hard",
                    "reason": "new edge",
                }
            ),
        )
        run_import(engine, taxonomy, "a" * 40)

        after = get(running, "/topics/mt_frac/prerequisites")
        assert [i["topic"]["id"] for i in after] == ["mt_placevalue", "mt_add2"]
        assert get(running, "/meta/source")["commit_sha"] == "a" * 40
    engine.dispose()


def test_the_importer_reloads_the_shared_graph(tmp_path: Path):
    taxonomy_graph.reload([], {})
    engine = migrate(tmp_path / "shared.db")

    run_import(engine, FIXTURE_TAXONOMY, FIXTURE_COMMIT)
    engine.dispose()

    assert taxonomy_graph.topic_count == 5
    assert taxonomy_graph.edge_count == 4
    assert [link.topic_id for link in taxonomy_graph.direct_prerequisites("mt_add2")] == [
        "mt_placevalue"
    ]


def test_the_service_works_without_http(client: TestClient):
    """The puzzle generator will call the service like this."""
    with Session(client.app.state.engine) as session:
        service = TaxonomyService(session, client.app.state.graph)

        page = service.list_topics(domain="Number")
        assert [topic.name for topic in page.items] == ["Place value", "Two-digit addition"]
        patterns = service.get_error_patterns("mt_add2")
        assert [p.distractor for p in patterns] == ["611", "61", None]
        assert service.get_step_back("mt_add2")[0].topic.id == "mt_placevalue"
        assert service.get_topic("mt_add2", "Mia").assessment_prompt.startswith("Can Mia")
        with pytest.raises(TopicNotFound) as error:
            service.get_topic("mt_nope")
        assert error.value.topic_id == "mt_nope"


def test_service_module_does_not_import_fastapi():
    source = (BACKEND_DIR / "app" / "taxonomy" / "service.py").read_text(encoding="utf-8")
    graph_source = (BACKEND_DIR / "app" / "taxonomy" / "graph.py").read_text(encoding="utf-8")
    assert "fastapi" not in source
    for module in ("fastapi", "sqlalchemy", "sqlmodel", "networkx"):
        assert f"import {module}" not in graph_source
        assert f"from {module}" not in graph_source

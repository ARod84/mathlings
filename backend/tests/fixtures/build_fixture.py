"""Writes the tiny fixture taxonomy in tests/fixtures/taxonomy/data.

Run it after editing the data below, so manifest.json gets fresh checksums:

    uv run python tests/fixtures/build_fixture.py

The fixture has the same file layout as os-taxonomy. What it contains:

    mt_add2        Mathematics 7-9    in scope, has research with 3 error patterns
    mt_placevalue  Mathematics 6-8    in scope, research with a null assess
    mt_frac        Mathematics 9-11   in scope, no research
    mt_count       Mathematics 4-6    too young; needed by mt_placevalue   (closure)
    mt_words       English 5-6        needed by mt_count                   (closure, not maths)
    mt_algebra     Mathematics 13-15  too old, and nothing in scope needs it (not imported)
    mt_forces      Science 7-9        unrelated                              (not imported)
"""

import hashlib
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "taxonomy" / "data"


def topic(id_, subject, domain, name, start, end, *, kind="PROCEDURAL", centrality=0.1):
    return {
        "id": id_,
        "type": kind,
        "subject": subject,
        "domain": domain,
        "name": name,
        "description": f"Fixture description of {name}.",
        "centrality": centrality,
        "evidence": [f"Shows {name.lower()} once", f"Explains {name.lower()}"],
        "assessmentPrompt": f"Can {{{{name}}}} show {name.lower()} and explain how they did it?",
        "standards": ["fixture-curriculum:FX-1"],
        "ageRangeStart": start,
        "ageRangeEnd": end,
    }


TOPICS = [
    topic("mt_add2", "Mathematics", "Number", "Two-digit addition", 7, 9),
    topic("mt_placevalue", "Mathematics", "Number", "Place value", 6, 8, kind="CONCEPTUAL"),
    topic("mt_frac", "Mathematics", "Fractions", "Unit fractions", 9, 11, centrality=None),
    topic("mt_count", "Mathematics", "Number", "Counting to twenty", 4, 6),
    topic("mt_words", "English", "Vocabulary", "Number words", 5, 6, kind="LANGUAGE"),
    topic("mt_algebra", "Mathematics", "Algebra", "Solving equations", 13, 15),
    topic("mt_forces", "Science", "Forces", "Pushes and pulls", 7, 9, kind="CONCEPTUAL"),
]


def edge(topic_id, prerequisite_id, strength="hard"):
    return {
        "topicId": topic_id,
        "prerequisiteId": prerequisite_id,
        "strength": strength,
        "reason": f"{topic_id} builds on {prerequisite_id}.",
    }


DEPENDENCIES = [
    edge("mt_add2", "mt_placevalue"),
    edge("mt_placevalue", "mt_count"),
    edge("mt_count", "mt_words", "soft"),
    edge("mt_frac", "mt_add2", "soft"),
    edge("mt_algebra", "mt_add2"),
]


def research(topic_id, assess):
    return {
        "topicId": topic_id,
        "pedagogy": {
            "summary": f"How to teach {topic_id}.",
            "bestPractices": ["Use concrete materials first"],
            "keyRepresentations": ["Base-ten blocks"],
            "commonMisconceptions": ["Digits are added without regard to place"],
        },
        "learn": {
            "summary": "A short activity sequence.",
            "activities": [{"title": "Build it", "steps": ["Make both numbers with blocks"]}],
            "constraints": [],
            "reviewNotes": [],
            "schemaVersion": 1,
        },
        "assess": assess,
        "sources": [{"title": "Fixture source", "url": "https://example.org/fixture"}],
        "confidence": "high",
        "provenance": {"author": "fixture"},
        "publicationNotes": {},
    }


ADD2_ASSESS = {
    "method": "diagnostic question",
    "poeTask": None,
    "probeDeeper": ["Ask how they know"],
    "correctAnswer": "71",
    "errorPatterns": [
        {
            "kind": "misconception",
            "pattern": "Adds each column separately and writes both sums: 43 + 28 = 611",
            "nextMove": "Build both numbers with tens and ones, then trade ten ones for a ten.",
            "distractor": "611",
            "revealedBy": "Writes 611",
            "reteachPrerequisiteId": "mt_placevalue",
        },
        {
            "kind": "performance",
            "pattern": "Forgets to add the carried ten",
            "nextMove": "Have them say the carried ten out loud before adding the tens.",
            "distractor": "61",
            "revealedBy": "Writes 61",
            "reteachPrerequisiteId": None,
        },
        {
            "kind": "developmental",
            "pattern": "Counts on by ones and loses track",
            "nextMove": "Offer a number line and count on in tens first.",
            "distractor": None,
            "revealedBy": "Answer is off by one or two",
            "reteachPrerequisiteId": "mt_count",
        },
    ],
    "responseLevels": {"secure": "Explains the trade"},
    "diagnosticPrompt": "What is 43 + 28?",
    "whatMakesItDiscriminate": "Needs a trade in the ones column.",
}

FORCES_ASSESS = {**ADD2_ASSESS, "correctAnswer": "It moves", "errorPatterns": []}

RESEARCH_RECORDS = [
    research("mt_add2", ADD2_ASSESS),
    research("mt_placevalue", None),
    research("mt_forces", FORCES_ASSESS),
]

CLUSTERS = [
    {
        "subject": "Mathematics",
        "domain": "Number",
        "ageRangeStart": 7,
        "summary": "Your child is adding bigger numbers.",
    },
    {
        "subject": "English",
        "domain": "Vocabulary",
        "ageRangeStart": 5,
        "summary": "Your child is learning number words.",
    },
    {
        "subject": "Science",
        "domain": "Forces",
        "ageRangeStart": 7,
        "summary": "Your child is exploring pushes and pulls.",
    },
]


def encode(payload) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(data_dir: Path = DATA_DIR) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    topics = encode({"version": "fixture-v1", "topicCount": len(TOPICS), "topics": TOPICS})
    files = {
        "topics.json": topics,
        "dependencies.json": encode(
            {
                "version": "fixture-v1",
                "note": "`topicId` depends on `prerequisiteId`.",
                "edgeCount": len(DEPENDENCIES),
                "dependencies": DEPENDENCIES,
            }
        ),
        "teaching-research.json": encode(
            {
                "schemaVersion": 1,
                "version": "fixture-v1",
                "exportedAt": "2026-01-01T00:00:00.000Z",
                "topicFileSha256": sha256(topics),
                "recordCount": len(RESEARCH_RECORDS),
                "coverage": {},
                "notes": [],
                "records": RESEARCH_RECORDS,
            }
        ),
        "clusters.json": encode(
            {"version": "fixture-v1", "clusterCount": len(CLUSTERS), "clusters": CLUSTERS}
        ),
    }
    manifest = {
        "dataset": "Fixture taxonomy",
        "taxonomyVersion": "fixture-v1",
        "files": {
            name: {"bytes": len(data), "sha256": sha256(data)} for name, data in files.items()
        },
    }
    for name, data in files.items():
        (data_dir / name).write_bytes(data)
    (data_dir / "manifest.json").write_bytes(encode(manifest))


if __name__ == "__main__":
    build()
    print(f"Wrote fixture taxonomy to {DATA_DIR}")

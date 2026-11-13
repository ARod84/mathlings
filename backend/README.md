# Mathlings backend

A FastAPI service and a SQLite database of learning topics. The topics come from the open dataset
[os-taxonomy](https://github.com/withmarbleapp/os-taxonomy); every game will be tied to a topic id.
The database answers two questions:

- **What does this topic require first?** The `prerequisite` table.
- **What mistakes do kids typically make here, and what should we do about them?** The
  `error_pattern` table.

The API is read-only; see [The API](#the-api) below.

Stack: Python 3.12, [uv](https://docs.astral.sh/uv/), FastAPI, SQLModel on SQLite, Alembic, pytest,
ruff, pydantic-settings.

## Setup

Run everything from `backend/`.

```bash
uv sync                                   # install dependencies
./scripts/fetch_taxonomy.ps1              # Windows: fetch the pinned dataset
./scripts/fetch_taxonomy.sh               # macOS, Linux, Git Bash: same
uv run alembic upgrade head               # create the database tables
uv run python -m app.taxonomy.importer    # load the dataset into the database
uv run uvicorn app.main:app --reload      # API at http://localhost:8000/health
```

| Command                                         | What it does                                 |
| ----------------------------------------------- | -------------------------------------------- |
| `uv run pytest`                                 | Tests, on a tiny fixture taxonomy            |
| `uv run pytest -m slow`                         | The real import against `vendor/os-taxonomy` |
| `uv run ruff check .`                           | Lint                                         |
| `uv run ruff format .`                          | Format                                       |
| `uv run python tests/fixtures/build_fixture.py` | Rebuild the fixture files after editing them |

## Settings

Read from the environment, or from `backend/.env`.

| Variable                  | Default                     | Meaning                                                 |
| ------------------------- | --------------------------- | ------------------------------------------------------- |
| `MATHLINGS_DATABASE_PATH` | `data/app.db`               | The SQLite file (gitignored)                            |
| `MATHLINGS_TAXONOMY_PATH` | `vendor/os-taxonomy`        | The dataset checkout (gitignored)                       |
| `MATHLINGS_CORS_ORIGINS`  | `["http://localhost:5173"]` | Browser origins allowed to call the API, as a JSON list |

## The pinned dataset

The dataset version is one constant: `TAXONOMY_COMMIT` in `app/taxonomy/constants.py`. The fetch
scripts read it from there and check out exactly that commit, and the importer refuses a checkout
at any other commit. To upgrade, change the constant, review the new data, update
`REVIEWED_COUNTS` next to it, then fetch and import again. There is no "latest".

## What gets imported

- **In scope:** topics with subject `Mathematics` whose age range overlaps 7–12.
- **Prerequisite closure:** every topic reachable from those through prerequisite edges, however
  young or whatever the subject, stored with `in_scope = false`. Without them, step-back paths
  would have holes.
- **Research, error patterns and clusters** only for the imported topics. A cluster is kept when an
  imported topic has its subject and domain.
- **Never imported:** `curriculum-standards.json`, `curriculum-alignments.json` and each topic's
  `standards` field. See [NOTICE.md](../NOTICE.md).

## Tables

| Table               | Holds                                                                                  |
| ------------------- | -------------------------------------------------------------------------------------- |
| `taxonomy_source`   | One row: commit, versions, file checksums, import time and the attribution text        |
| `topic`             | The topics; `assessment_prompt_template` keeps the raw `{{name}}` placeholder          |
| `prerequisite`      | `topic_id` depends on `prerequisite_id`, with `strength` (hard or soft) and `reason`   |
| `teaching_research` | One row per topic: `pedagogy`, `learn`, `assess`, `sources` as JSON, plus `confidence` |
| `error_pattern`     | One row per typical mistake, taken out of `assess.errorPatterns`                       |
| `cluster`           | Parent-friendly summaries per subject, domain and age band                             |

In `error_pattern`, `distractor` feeds wrong answer options, `next_move` feeds hints, and
`reteach_prerequisite_id` says which topic to step back to. `position` is the mistake's place in
the upstream list; with `topic_id` it identifies the row, so ids survive a re-import.

The schema lives in `alembic/versions/`. A test fails if the migration and `app/models.py` drift
apart.

## How the importer behaves

Before writing anything it:

1. checks each data file's SHA-256 against `manifest.json`;
2. checks that `teaching-research.json` was exported for this `topics.json` (`topicFileSha256`);
3. finds dependencies and `reteachPrerequisiteId` values that point at unknown topics, logs them
   and skips them (a bad edge is dropped; an error pattern is kept with its reference cleared);
4. checks that the imported prerequisite graph has no cycles.

A checksum problem or a cycle stops the import with nothing written. Everything is written in one
transaction, so a failure part-way leaves the previous data as it was.

Running it again changes nothing, not even ids or the import time. When the pinned commit changes,
rows are updated in place and the summary lists what was added, changed and removed per table.

## Assessment prompts

`app.taxonomy.prompts.render_assessment_prompt(template, name)` fills the `{{name}}` placeholder.
Without a name it rewords the prompt to speak to the reader: "If {{name}} writes..., can they..."
becomes "If you write..., can you...".

## The API

All routes are `GET` under `/api/v1`. Interactive docs are at `http://localhost:8000/docs`.

| Route                         | Returns                                                               |
| ----------------------------- | --------------------------------------------------------------------- |
| `/domains`                    | Domains with topic counts                                             |
| `/topics`                     | A page of topic summaries: `{items, total, limit, offset}`            |
| `/topics/{id}`                | The full topic, with the assessment prompt rendered (`?name=`)        |
| `/topics/{id}/prerequisites`  | What it requires first (`?depth=direct\|all`, `?strength=hard\|soft`) |
| `/topics/{id}/unlocks`        | Topics that directly depend on it                                     |
| `/topics/{id}/step-back`      | Where to step back to, best candidate first                           |
| `/topics/{id}/error-patterns` | Typical mistakes, each with its reteach topic                         |
| `/topics/{id}/research`       | Trimmed teaching research; 404 if the topic has none                  |
| `/meta/source`                | Pinned commit, taxonomy version, import time and attribution          |

`/topics` filters: `domain`, `in_scope` (default true), `age`, `type`, `q`, `has_research`, plus
`limit` (default 50, max 200) and `offset`. `GET /health` also says whether the taxonomy is loaded
and how many topics it has. An unknown topic gives a 404 with
`{"detail": "Topic not found", "topic_id": "..."}`.

### Layers

| File                      | Role                                                                         |
| ------------------------- | ---------------------------------------------------------------------------- |
| `app/taxonomy/service.py` | `TaxonomyService`: every query. No FastAPI. Python code calls this directly. |
| `app/taxonomy/graph.py`   | The prerequisite graph in memory. Standard library only.                     |
| `app/taxonomy/schemas.py` | Pydantic response models. Database tables are never returned.                |
| `app/api/v1/taxonomy.py`  | Thin routes: parse the request, call the service.                            |

```python
from sqlmodel import Session
from app.db import make_engine
from app.taxonomy.service import TaxonomyService, reload_graph

with Session(make_engine()) as session:
    reload_graph(session)  # once per process
    service = TaxonomyService(session)
    patterns = service.get_error_patterns("mt_SrrsLiJkr3")
    step_back = service.get_step_back("mt_SrrsLiJkr3")
```

The graph is loaded once when the API starts. Each request then makes one small query to see
whether the database has been re-imported since, and reloads the graph if so; that is how a
re-import takes effect without a restart, even though the importer runs as a separate process.

### OpenAPI

`uv run python scripts/export_openapi.py` writes `openapi.json` at the repo root, for the
frontend's typed client. A test fails if that file is out of date.

## Puzzles

`app/puzzles` is a pure Python library for the first puzzle type, the **missing-number chain**:
one to four linked equations with one box each, where each answer becomes a visible number in the
next step.

```
8 + □ = 11      → 3
□ − 3 = 5       → 8     (the 3 is now visible)
14 − □ = 8      → 6     (so is the 8)
```

It has three parts that are kept separate on purpose.

| Part      | File           | Job                                                                                         |
| --------- | -------------- | ------------------------------------------------------------------------------------------- |
| Generator | `generator.py` | Builds a puzzle from `(seed, level, length)`. Same inputs, same puzzle.                     |
| Verifier  | `verifier.py`  | Checks a puzzle without trusting the generator: it solves each step by trying every number. |
| Diagnoser | `diagnoser.py` | Says which known mistake produced a wrong answer, and where to step back to.                |

`verified.generate_verified(...)` is the only way to get a puzzle meant for a child: it generates,
verifies, and retries with a derived seed if either fails. `verified.regenerate(puzzle_id)` rebuilds
a puzzle from its id alone, so nothing needs storing.

```python
from sqlmodel import Session
from app.db import make_engine
from app.puzzles.diagnoser import diagnose
from app.puzzles.taxonomy_link import first_step_back, load_catalog, topic_exists
from app.puzzles.verified import generate_verified
from app.taxonomy.service import TaxonomyService, reload_graph

with Session(make_engine()) as session:
    service = TaxonomyService(session, reload_graph(session))
    catalog = load_catalog(service)  # resolve the rule mapping once

puzzle = generate_verified(
    42, level=1, length=3, catalog=catalog, topic_exists=topic_exists(service)
)
diagnosis = diagnose(puzzle, 0, 19, catalog=catalog, step_back=first_step_back(service))
```

### Levels

| Level | Numbers                                    | Primary topic                                     | Also tagged                                                    |
| ----- | ------------------------------------------ | ------------------------------------------------- | -------------------------------------------------------------- |
| 1     | 0–20                                       | `mt_3JgrHY221M` Unknown in Addition & Subtraction | `mt_oIzycTBeE4` What the equals sign means, on answer-left use |
| 2     | 0–100                                      | `mt_3JgrHY221M`                                   | same                                                           |
| 3     | 0–1000, a three-digit number in every step | `mt_XuHmIn2xje` Missing number problems (age 7+)  | `mt_ehGS_uVSJv` Inverse: addition undoes subtraction           |

### Mistake rules

Each rule is a pure function of one step (`rules.py`, which has the full table per form).

| Rule                    | What the child does                                        | Example               | Taxonomy error pattern               |
| ----------------------- | ---------------------------------------------------------- | --------------------- | ------------------------------------ |
| `ADD_VISIBLE`           | Adds the two numbers they can see                          | `8 + □ = 11` → 19     | `mt_3JgrHY221M#0`, `mt_XuHmIn2xje#0` |
| `ANSWER_LEFT_BACKWARDS` | Reads `c = □ − b` as `c − b`                               | `5 = □ − 3` → 2       | `mt_3JgrHY221M#1`                    |
| `POSITION_CONFUSION`    | Treats `□ − b = c` as `c − b`                              | `□ − 120 = 250` → 130 | `mt_XuHmIn2xje#2`                    |
| `PLACE_VALUE_SLIP`      | Level 3: works column by column, no exchange or carry      | `245 + □ = 380` → 145 | none                                 |
| `OFF_BY_ONE_OVER/UNDER` | Counting slip, one too many or one too few                 | 3 → 4 or 2            | none                                 |
| `NEAR_MISS`             | Not a mistake: a filler near the answer when rules run out | 3 → 5                 | none                                 |

An error pattern id is `<topic id>#<position>`. `misconceptions.py` holds the mapping and resolves
it against the database at startup; it fails loudly if a pattern is missing or ambiguous.

### Quality report

```bash
uv run python -m app.puzzles.report --all --count 5000   # or --level 1
uv run python -m app.puzzles.report --samples 2          # example puzzles
uv run python -m app.puzzles.report --catalog            # rule -> error pattern table
```

Bump `GENERATOR_VERSION` in `levels.py` whenever a change can alter the puzzle a seed produces. A
puzzle also depends on the pinned taxonomy commit, through the error-pattern ids and hint sources.

### Puzzle API

`app/puzzles/service.py` (`PuzzleService`, no FastAPI) and the thin routes in
`app/api/v1/puzzles.py` put the library on HTTP, under `/api/v1/puzzles`.

| Route                                         | Body or params                                   | Returns              |
| --------------------------------------------- | ------------------------------------------------ | -------------------- |
| `POST /missing-number`                        | `{ level: 1–3, length: 1–4 (default 3), seed? }` | `PuzzlePublic` (201) |
| `GET /{puzzle_id}`                            |                                                  | `PuzzlePublic`       |
| `POST /{puzzle_id}/steps/{index}/check`       | `{ answer: 0–10000 }`                            | `CheckResult`        |
| `GET /{puzzle_id}/steps/{index}/hints/{tier}` | tier 1–3                                         | `{ tier, text }`     |

- **Stateless.** Every request rebuilds the puzzle from its id (`verified.regenerate`) and verifies
  it again. Nothing is stored.
- **Public shape.** `PuzzlePublic` has the equations, four shuffled `options` per step and
  `hint_tiers`. The order of the options is fixed by the puzzle id and step, so a reload looks the
  same. Answers, rule names, error-pattern ids and hint text stay on the server.
- **Answers are not secrets.** A later step shows the previous answer as a visible number; that is
  the puzzle. See the note in `app/puzzles/schemas.py` and the root README before changing it.
- **Checking.** A wrong check never gives the answer. It names the matched mistake rules (for
  analytics, not for the child) and the topic to step back to. Only hint tier 3 shows a worked step.
- **Errors.** Tampered or malformed id: 404. Id from an older generator version: 410 with
  `current_version`. Step or tier out of range: 404. Bad body or seed: 422. Generation out of
  retries, or a taxonomy without the puzzle topics: 503.
- **Catalog.** The mistake-rule catalog is resolved once at startup, next to the prerequisite
  graph, and again only when the graph reloads after a re-import.
- **Check log.** Each check writes one line to the `app.puzzles.checks` logger: puzzle id, step,
  correct, matched rules and latency. The same fields are on the record as `puzzle_check`. No
  personal data, and not the answer itself.

# Mathlings backend

A FastAPI service and a SQLite database of learning topics. The topics come from the open dataset
[os-taxonomy](https://github.com/withmarbleapp/os-taxonomy); every game will be tied to a topic id.
The database answers two questions:

- **What does this topic require first?** The `prerequisite` table.
- **What mistakes do kids typically make here, and what should we do about them?** The
  `error_pattern` table.

So far the API has one endpoint, `GET /health`.

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

| Variable                  | Default              | Meaning                           |
| ------------------------- | -------------------- | --------------------------------- |
| `MATHLINGS_DATABASE_PATH` | `data/app.db`        | The SQLite file (gitignored)      |
| `MATHLINGS_TAXONOMY_PATH` | `vendor/os-taxonomy` | The dataset checkout (gitignored) |

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

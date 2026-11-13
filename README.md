# Mathlings

Short math-logic puzzle games for kids aged 7–12. A standalone precursor to the Martians Space
Club site, to be merged into it later.

| Folder                  | What it is                                                                |
| ----------------------- | ------------------------------------------------------------------------- |
| [`frontend/`](frontend) | The games: Vite, React and TypeScript. Design system, `GameShell`, games. |
| [`backend/`](backend)   | Python API (FastAPI): the topic database, puzzle generation and checking. |
| [`shared/`](shared)     | Data both apps read: which taxonomy topics each game practises.           |

Each folder has its own README with setup and commands.

## Running both apps together

The frontend calls the backend, so run both. Two terminals:

```bash
# terminal 1: the API on http://localhost:8000
cd backend
uv sync
./scripts/fetch_taxonomy.ps1            # first time only (use fetch_taxonomy.sh on macOS or Linux)
uv run alembic upgrade head             # first time only
uv run python -m app.taxonomy.importer  # first time only
uv run uvicorn app.main:app --reload

# terminal 2: the games on http://localhost:5173
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server passes every `/api` request on to port 8000, so the
browser only talks to one origin. Number Pyramid works without the backend; Missing Number Chains
needs it, and shows a "Try again" message when it cannot reach it.

## The games

- **Number Pyramid.** Every block is the sum of the two blocks below it; the child drops number
  tiles into the empty blocks. Eight generated puzzles per round, made in the browser.
- **Missing Number Chains.** Equations with one missing number, linked in a chain: the number found
  in one step turns up in the next. Three levels (up to 20, 100 or 1000), five puzzles per round.
  The puzzles, the answer checks and the hints come from the backend.

## The API

`backend/` serves a JSON API under `/api/v1`, with interactive docs at
`http://localhost:8000/docs`. `openapi.json` at the repo root is the exported contract.

| Area     | Routes                                                                                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Taxonomy | `GET /domains`, `/topics`, `/topics/{id}` and its `/prerequisites`, `/unlocks`, `/step-back`, `/error-patterns`, `/research`; `GET /meta/source`                   |
| Puzzles  | `POST /puzzles/missing-number`, `GET /puzzles/{puzzle_id}`, `POST /puzzles/{puzzle_id}/steps/{index}/check`, `GET /puzzles/{puzzle_id}/steps/{index}/hints/{tier}` |
| Health   | `GET /health`                                                                                                                                                      |

### Puzzles are stateless

Nothing about a puzzle is stored. A `puzzle_id` such as `mnc-2-1-3-2-e12d` spells out the generator
version, level, number of steps and seed, plus a short checksum. On every request the server builds
the puzzle again from the id and verifies it before using it. Two consequences:

- An id that was tampered with fails its checksum and gets a 404.
- An id from an older generator version gets a `410 Gone` with the current version, and the
  frontend starts a new puzzle.

### Answers are not secrets

The browser receives a cut-down puzzle: equations, four answer options per step and the number of
hint tiers. It does not receive answers, mistake-rule names, error-pattern ids or hint text, and a
wrong check never says what the right answer was.

One thing is known and accepted: in a chain, each step shows the previous step's answer as a
visible number, because that is how the puzzle works. The frontend reveals steps one at a time.
This is a practice game for children, not an exam. The aim is to keep the answer out of the way
until the child has tried, not to make it impossible to find, so please do not "fix" this by hiding
later steps or encrypting anything.

## Data and licenses

The backend's topic data comes from the open Marble Skill Taxonomy. See [NOTICE.md](NOTICE.md) for
what we use from it and its licenses.

# Mathlings

Short math-logic puzzle games for kids aged 7–12. A standalone precursor to the Martians Space
Club site, to be merged into it later.

| Folder                  | What it is                                                                |
| ----------------------- | ------------------------------------------------------------------------- |
| [`frontend/`](frontend) | The games: Vite, React and TypeScript. Design system, `GameShell`, games. |
| [`backend/`](backend)   | Python API (FastAPI): the topic database, puzzle generation and checking. |

Each folder has its own README with setup and commands. The backend serves the taxonomy and the
puzzles over HTTP (see [The API](#the-api)); the frontend does not call it yet.

```bash
# frontend
cd frontend && npm install && npm run dev

# backend (see backend/README.md for the taxonomy import)
cd backend && uv sync && uv run uvicorn app.main:app --reload
```

## The API

`backend/` serves a JSON API under `/api/v1`, with interactive docs at
`http://localhost:8000/docs`. `openapi.json` at the repo root is the exported contract.

| Area     | Routes                                                                                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Taxonomy | `GET /domains`, `/topics`, `/topics/{id}` and its `/prerequisites`, `/unlocks`, `/step-back`, `/error-patterns`, `/research`; `GET /meta/source`                   |
| Puzzles  | `POST /puzzles/missing-number`, `GET /puzzles/{puzzle_id}`, `POST /puzzles/{puzzle_id}/steps/{index}/check`, `GET /puzzles/{puzzle_id}/steps/{index}/hints/{tier}` |
| Health   | `GET /health`                                                                                                                                                      |

### Puzzles are stateless

Nothing about a puzzle is stored. A `puzzle_id` such as `mnc-1-1-3-2-b555` spells out the generator
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

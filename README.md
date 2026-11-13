# Mathlings

[![CI](https://github.com/ARod84/mathlings/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ARod84/mathlings/actions/workflows/ci.yml?query=branch%3Adev)

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
uv run alembic upgrade head             # first time, and after pulling a new migration
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
  in one step turns up in the next. Three levels (up to 20, 100 or 1000), five puzzles per round. "Play" lets the backend
  pick the level and chain length puzzle by puzzle; the child can also choose a range. When a
  child keeps making the same known mistake, every other puzzle is built to target it. The child
  is never told.
  The puzzles, the answer checks and the hints come from the backend.

## The API

`backend/` serves a JSON API under `/api/v1`, with interactive docs at
`http://localhost:8000/docs`. `openapi.json` at the repo root is the exported contract.

| Area     | Routes                                                                                                                                                                                       |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Taxonomy | `GET /domains`, `/topics`, `/topics/{id}` and its `/prerequisites`, `/unlocks`, `/step-back`, `/error-patterns`, `/research`; `GET /meta/source`                                             |
| Puzzles  | `POST /puzzles/{game}` (`missing-number` or `sequences`), `GET /puzzles/{puzzle_id}`, `POST /puzzles/{puzzle_id}/steps/{index}/check`, `GET /puzzles/{puzzle_id}/steps/{index}/hints/{tier}` |
| Players  | `GET /players/me/summary`, `GET /players/me/next`, `DELETE /players/me`; all need the `X-Player-Id` header (see [Privacy](#privacy))                                                         |
| Health   | `GET /health`                                                                                                                                                                                |

### Puzzles are stateless

No puzzle is stored. A `puzzle_id` such as `mnc-3-1-3-2-8c3f` spells out the generator
version, level, number of steps and seed, plus a short checksum (and, for a puzzle built to
target one mistake, a two-letter focus code). On every request the server builds
the puzzle again from the id and verifies it before using it. Two consequences:

- An id that was tampered with fails its checksum and gets a 404.
- An id from an older generator version gets a `410 Gone` with the current version, and the
  frontend starts a new puzzle.

What can be stored is practice history, and only for a browser that sends a player id. That is the
[Privacy](#privacy) section below.

### Answers are not secrets

The browser receives a cut-down puzzle: equations, four answer options per step and the number of
hint tiers. It does not receive answers, mistake-rule names, error-pattern ids or hint text, and a
wrong check never says what the right answer was.

One thing is known and accepted: in a chain, each step shows the previous step's answer as a
visible number, because that is how the puzzle works. The frontend reveals steps one at a time.
This is a practice game for children, not an exam. The aim is to keep the answer out of the way
until the child has tried, not to make it impossible to find, so please do not "fix" this by hiding
later steps or encrypting anything.

## Privacy

Mathlings is for children, so it keeps as little as it can.

**What is stored.** For a browser that sends an `X-Player-Id` header, the backend keeps anonymous
practice history for Missing Number Chains, in three tables:

| Table          | One row per         | Holds                                                                                                                                                                     |
| -------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `player`       | player id           | The id, when it was first seen and when it was last seen                                                                                                                  |
| `attempt`      | checked answer      | Puzzle id, level, step, the answer given, right or wrong, the matched mistake rules and topics, which try at the step it was, and the highest hint tier fetched before it |
| `hint_request` | hint tier asked for | Puzzle id, step, tier and time                                                                                                                                            |

**What is not stored.** No name, email, birthday or age. No IP address and no user agent. No
cookies are set. The player id is not written to the logs. Number Pyramid runs in the browser and
sends nothing. Without the header the API stores nothing at all and answers exactly as it did
before this feature existed.

**The player id is pseudonymous, not a login.** It is a random UUID (version 4) that the browser
makes on first play and keeps in `localStorage` under `mathlings.playerId`. The server never makes
one and never sends one back. It is not authentication: anyone who has the id can read or delete
its history. That is acceptable here only because the history is anonymous practice data. Nothing
personal may ever be attached to it. If the browser blocks `localStorage` (private mode, for
example), no id is made, no header is sent and nothing is stored; the game plays as usual.

**Deleting.** "Forget my progress on this device" at the bottom of the home screen asks once, then
calls `DELETE /api/v1/players/me`. That removes the player row and every attempt and hint row. It
is a real delete, not a flag. The browser then drops its id, and the next play starts a new one.
Deleting an id the server has never seen also answers `204`. If the server cannot be reached, the
id is kept so the delete can be tried again.

**What it is used for.** The backend replays a player's first tries to estimate how well they
know each topic, and recommends the next level and chain length for Missing Number Chains
(`GET /players/me/next`). Nothing extra is stored for this, and the estimate, the reason and the
mistake it flags are never shown to the child. How it works, and how well, is in the
[backend README](backend/README.md#adaptive-practice).

**Open item: no retention policy yet.** History is kept until someone deletes it. There is no
expiry, no clean-up job and no rule for players who never come back. This has to be decided before
the app is used by real children; it is deliberately not invented here.

## Continuous integration

GitHub Actions, in `.github/workflows/`. No secrets are needed.

| Workflow   | Runs on                                         | Jobs                                                                                                                                                                                                |
| ---------- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ci.yml`   | Every push and pull request to `dev` and `main` | **Backend**: `uv sync --locked`, ruff lint and format check, every migration applied to a new empty database, `pytest -m "not slow"`, and a check that `openapi.json` matches the code.             |
|            |                                                 | **Frontend**: `npm ci`, typecheck, lint, format check, tests (one of them compares `schema.d.ts` with `openapi.json`) and build.                                                                    |
| `slow.yml` | By hand ("Run workflow"), and every Monday      | **Slow tests**: fetches the pinned taxonomy, migrates, imports, then `pytest -m slow`. The false-promotion target shows as an expected failure, and the job fails the day that test starts passing. |

A new push cancels the run still going for the same branch. The Python version comes from
`backend/.python-version` and the Node version from `frontend/.nvmrc`. A schedule only runs from
the default branch, so the weekly run starts once `slow.yml` is on `main`, and tests `main`.

### Branch protection

Not set up by the workflow; do it once in the repository settings. For `main` (repeat for `dev`
if wanted):

1. **Settings → Branches → Add branch ruleset** (or "Add classic branch protection rule").
2. Target branch: `main`.
3. Turn on **Require a pull request before merging**.
4. Turn on **Require status checks to pass**, and add these two checks by name:
   - `Backend`
   - `Frontend`
5. Optional: **Require branches to be up to date before merging**, so the checks ran on the
   merged result.
6. Save.

The names are the job names in `ci.yml`. GitHub only offers a check in the search box after it
has run at least once on the repository. Do not require `Slow tests`: it does not run on pull
requests, so a pull request would wait for it for ever.

## Data and licenses

The backend's topic data comes from the open Marble Skill Taxonomy. See [NOTICE.md](NOTICE.md) for
what we use from it and its licenses.

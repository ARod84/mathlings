# Mathlings

Short math-logic puzzle games for kids aged 7–12. A standalone precursor to the Martians Space
Club site, to be merged into it later.

| Folder                  | What it is                                                                |
| ----------------------- | ------------------------------------------------------------------------- |
| [`frontend/`](frontend) | The games: Vite, React and TypeScript. Design system, `GameShell`, games. |
| [`backend/`](backend)   | Python API (FastAPI) and the database of topics the games are tied to.    |

Each folder has its own README with setup and commands. The two are not connected yet: the backend
only serves `/health`, and the frontend does not call it.

```bash
# frontend
cd frontend && npm install && npm run dev

# backend (see backend/README.md for the taxonomy import)
cd backend && uv sync && uv run uvicorn app.main:app --reload
```

The backend's topic data comes from the open Marble Skill Taxonomy. See [NOTICE.md](NOTICE.md) for
what we use from it and its licenses.

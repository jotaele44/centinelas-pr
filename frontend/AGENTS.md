# AGENTS.md

## Project Context

This is the Centinelas-PR frontend: a Vite + React 18 + Tailwind + Radix/shadcn app.
It serves two independent surfaces:

1. **Legislative monitor** (existing): the Puerto Rico civic pre-officialization
   lifecycle — `Signal` → `Matter` → handoff to MoneySweep as an `OfficialRecord`.
   Pages like `Signals`, `Matters`, `Handoff`, `LawTable`, `Authors`. These are
   backed by `src/api/appClient.js`, a localStorage adapter seeded from
   `src/data/seedData.js` — **no backend process required** for these pages.

2. **Universal intake pipeline** (`/pipeline`): visibility into the 6-domain
   classify-and-route engine (the Python `centinelas` package). These pages are
   backed by `src/api/pipelineClient.js`, which talks over HTTP to the FastAPI
   server at `server/backend/main.py`. This surface needs the backend running to
   show real data.

> Base44 has been fully removed. There is no `@base44/sdk`, no Base44 Vite plugin,
> and no `base44` CLI. Do not reintroduce them.

## Key Files

- `src/` — frontend application source.
- `src/api/appClient.js` — localStorage adapter for the 21 legislative entities.
- `src/api/pipelineClient.js` — REST client for the universal-pipeline FastAPI backend (`VITE_API_BASE`).
- `../server/backend/main.py` — the FastAPI backend the pipeline pages read from.
- `vite.config.js` — plain `@vitejs/plugin-react` + `@` path alias (no Base44 plugin).
- `.env` — local env values (copy from `.env.example`); never commit secrets.

## Working Notes

- `npm run dev` — starts the Vite dev server on :5173. Sufficient on its own for the
  legislative pages.
- For the `/pipeline` pages to show real data, also run the backend from the **repo root**:
  ```bash
  pip install -e ".[server]"        # once
  uvicorn server.backend.main:app --reload --port 8000
  ```
  Point the frontend at it via `VITE_API_BASE` in `.env` (defaults to `http://localhost:8000`).
- Run the relevant checks from `package.json` before finishing code changes:
  `npm run lint`, `npm run typecheck`, `npm run build`.

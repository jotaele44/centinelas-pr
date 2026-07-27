# centinelas-pr — Professional Maturity Audit

**Date:** 2026-07-26 · **Method:** static review **plus execution** — every number below came
from running the code in a clean container (Python 3.11.15, Node v22.22.2). Setup followed
this repo's own `hub_callable_commands.setup` (`uv pip install --system -e ".[dev]"`).

Scope: this repository only. Cross-repo comparisons live in
[`thehub-pr/docs/FEDERATION_MATURITY_AUDIT.md`](https://github.com/jotaele44/thehub-pr/blob/main/docs/FEDERATION_MATURITY_AUDIT.md).

---

## Scorecard

| Dim | Area | Score | Evidence |
|---|---|---|---|
| D1 | Functional completeness | **3** | 6-domain classify-and-route pipeline is real and tested; the legislative surface is a documented localStorage adapter |
| D2 | Data reality | **3** | `data/signals/live_signals.jsonl` carries **254 records all flagged `is_synthetic: false`**; the only synthetic rows are 6 in the clearly-named `example_signals.jsonl`. `federation.json` exports the live ledger. |
| D3 | UI craft | **4** | 16 pages, 4.6k LOC, 35 `aria-*`, 10 `role=`; `components/ListState.jsx` gives a proper three-way loading/error/empty split (with `aria-live` and `role="alert"`) and is used by 8 files. Missing only a global `ErrorBoundary`. |
| D4 | Test coverage | **3** | `139 passed` (2.7s), 19 test files — proportionate to 5.4k LOC of Python. **Zero frontend tests.** |
| D5 | Engineering hygiene | **3** | `ruff check .` clean, but on a narrow rule set (`E4,E7,E9,F`); no mypy in CI |
| D6 | Doc accuracy | **4** | `frontend/AGENTS.md` is excellent — it states plainly that `appClient.js` is a localStorage adapter needing no backend |

**Overall: a well-documented small repo with one serious honesty problem in its UI.**
The engineering is sound for its size and the data is real — 254 live signal records. The
issue is that the login screen presents a credential check that does not exist, on a repo
that declares itself `PRODUCTION`.

---

## The headline finding: the sign-in form authenticates nothing

`frontend/src/api/appClient.js` implements auth entirely in `localStorage`, never contacting
a server. This is *documented* — `frontend/AGENTS.md` says the legislative surface is
"backed by `src/api/appClient.js`, a localStorage adapter … **no backend process required**".
The adapter is not the problem. Presenting it behind an email/password/SSO form is.

| Method | Line | Behaviour |
|---|---|---|
| `loginViaEmailPassword(email)` | `:323` | **Takes no password parameter at all.** Any email returns a token and writes an admin user. |
| `verifyOtp({email})` | `:331` | Accepts **any** OTP code. |
| `loginWithProvider(_provider, redirectTo)` | `:345` | The "Continue with Google" button writes `DEFAULT_USER` and redirects. No OAuth. |
| `me()` | `:320` | Returns `DEFAULT_USER` when nothing is stored — a visitor who never logs in is **already** `{id: "local-admin", role: "admin"}` (`:12-17`). |
| `resetPassword()` | `:342` | Returns `{status: "reset"}`. Nothing is reset. |

`App.jsx` had no `ProtectedRoute` and no `requireAuth`, so nothing was gated regardless.
Confirmed against a live server: this repo's backend serves 13 routes (`/items`, `/queue`,
`/sources`, `/status`, …) and **no `/auth/*` endpoint of any kind** — there is no server-side
auth to reach even if the client tried.

The risk is not that an attacker bypasses a check. It is that an operator sees a password
field and a Google button on a repo marked `PRODUCTION` and reasonably concludes the page is
protected. It is not, and it never was.

---

## What is fully developed vs. what is not

**PRODUCTION**

| Module | Evidence |
|---|---|
| `src/centinelas/` (16 files, 1,637 LOC) | 6-domain classify-and-route engine; covered by the 139-test suite |
| `server/backend/main.py` | 13 routes (`/items`, `/items/{id}`, `/queue`, `/sources`, `/status`, …); the `/pipeline` UI reads these live |
| `frontend/src/api/pipelineClient.js` | real REST client over `VITE_API_BASE`; the one frontend path that talks to a backend |
| Handoff to `moneysweep-pr` | `Signal` → `Matter` → `OfficialRecord`; dispatch workflows for aguayluz and ovnis; `handoff-ack.yml` |
| `skills/` + `skill-registry.yaml` | validated by `skills-validation.yml` in CI |

**FUNCTIONAL**

| Module | Gap |
|---|---|
| `frontend/src/api/appClient.js` | 21 entities over `localStorage`, seeded from `src/data/seedData.js`. Works as designed; not a backend. |
| Legislative pages (Signals, Matters, Entities, SignalsTable) | fully interactive, but every write lands in browser storage only |

**SCAFFOLD**

| Item | Why |
|---|---|
| Global error handling | `ListState.jsx` covers list-level error and empty states well, but there is no app-level `ErrorBoundary`, so a render-time crash outside a list takes the page down blank |

**DEAD** — *fixed in this PR.*

| Item | Proof |
|---|---|
| Login / Register / ForgotPassword / ResetPassword | See above. No `/auth/*` route exists on the backend; the client methods verify nothing. |

---

## UI feature matrix

| Page | Backing data | Real backend? | Verdict |
|---|---|---|---|
| Pipeline, PipelineItemDetail | `pipelineClient.js` → FastAPI `/items`, `/queue` | **Yes** | **Production** |
| Handoff | `pipelineClient.js` → `getHandoffs()` / `createHandoff()` → `POST /handoffs/{itemId}` | **Yes** | **Production** |
| Monitor, Sources | mixed | partial | **Functional** |
| Signals, SignalsTable, Matters, MatterDetail, Entities, EntityDetail, Home | `appClient.js` → `localStorage` | No, by design | **Functional (local-only)** |
| Login, Register, ForgotPassword, ResetPassword | `appClient.js` auth stubs | No | **Dead**, now gated |

---

## Fix applied in this PR

**Auth routes render only when auth is actually required.**
`frontend/src/App.jsx` now reads `appPublicSettings?.public_settings?.auth_required` — the
flag `lib/AuthContext.jsx:27` already sets (currently hardcoded `false`, alongside
`runtime: 'platform-neutral-local-adapter'`) — and redirects `/login`, `/register`,
`/forgot-password`, `/reset-password` to `/` while it is false. The capitalized back-compat
aliases (`/Login`, `/Register`, …) still redirect to their lowercase paths, so no existing
link breaks.

This does not weaken anything: there was no protection to weaken. It stops the app
advertising a credential check it cannot perform. The pages remain in the tree, so flipping
`auth_required` to `true` the day a real authenticating backend lands brings them straight
back.

Verified per `frontend/AGENTS.md`'s required checks: `npm run lint` clean,
`npm run typecheck` clean, `npm run build` clean (373 kB gzip 113 kB), `pytest` `139 passed`
unchanged.

---

## Backlog, ranked

| # | Item | Effort | Why it matters |
|---|---|---|---|
| 1 | Decide the auth story, then either implement `/auth/*` server-side or delete the four pages | **L** / **S** | This PR stops the lie; it does not resolve it. A repo declaring `PRODUCTION` should not ship a decorative login. |
| 2 | Add a global `ErrorBoundary` | **S** | `ListState.jsx` handles list-level failures; a crash outside a list still blanks the page. |
| 3 | Extend the `ListState` pattern to the remaining pages | **S** | 8 of 16 pages use it today; the rest would benefit from the same three-way split. |
| 4 | Add a frontend test runner and smoke tests | **M** | 4.6k LOC of UI, zero tests. Copy the vitest + Testing Library setup from `thehub-pr/server/frontend`. |
| 5 | Widen the ruff rule set beyond `E4,E7,E9,F` and add mypy | **S** | `aguayluz-pr` already runs `E,F,I,B,UP,SIM,W` cleanly at a similar size — the bar is reachable. |
| 6 | Rename `auth_required` → `requires_auth` to match `thehub-pr`/`skywatcher-pr` | **S** | Same concept, two keys, one federation. |

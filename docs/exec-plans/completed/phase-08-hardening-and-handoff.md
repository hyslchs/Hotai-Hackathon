# Phase 8: repeatable startup, safety audit, and demonstration handoff

## Purpose and observable outcome

A new contributor can follow one beginner-friendly README path to prepare permitted artifacts, start the three local services, and demonstrate the mobile flow within two minutes. Before presenting, one command verifies the database, generated serving inputs, fallback data, backend, frontend, and necessary local configuration. The repository contains no committed raw trips, secrets, real rider mapping, or stored restricted provider response.

## Progress

- 2026-09-21T00:00:37Z — In progress: Phase 7 completed and archived with PostgreSQL and E2E evidence.
- 2026-09-21T00:08:00Z — Completed Milestone 1: Docker build context now excludes .env and data; Compose runs PostgreSQL, migration, read-only aggregate loader, healthy backend, then frontend. A local port-55432 Compose startup completed migration/load and reached healthy frontend/backend.
- 2026-09-21T00:12:00Z — Completed Milestone 2: added fail-closed scripts/demo_check.py and wired make demo-check. It passed against the live stack and deliberately returned exit code 1 for an unreachable backend.
- 2026-09-21T00:16:00Z — Completed Milestone 3: five mobile Chromium E2E scenarios passed against the live Compose stack. No-key Places/Routes fallback returned five synthetic restaurants; LLM-disabled template rendered deterministically.
- 2026-09-21T00:24:30Z — Completed Milestone 4: README two-minute script, candidate-tree scan, Make command-surface acceptance, current PostgreSQL benchmark, and Definition-of-Done audit completed.

## Surprises and discoveries

- The existing README still says Phases 4–8 are not implemented and its `make demo-check` target is intentionally a placeholder. It cannot be used as handoff documentation.
- Existing Compose starts an empty PostgreSQL database but neither applies migrations nor loads the serving artifacts, so its advertised frontend path cannot yet work in a fresh local volume.
- This Git repository currently has zero tracked files. A zero-violation safety result alone therefore does not prove a future commit is safe; the final report must state that limitation and run content scans over the candidate working-tree files too.
- The existing PostgreSQL port 5432 was occupied in this environment. The tested Compose configuration used the documented POSTGRES_PORT=55432 override; Docker-internal connections remain on 5432.
- The original safety scan correctly blocked raw-data paths but also blocked the intentionally tracked data/raw/.gitkeep placeholder. The final rule permits only .gitkeep placeholders while continuing to reject actual raw/CSV/Parquet paths.

## Decision log

- 2026-09-21 — Compose may mount locally generated aggregate/model artifacts read-only for its one-shot loader, but must never copy raw trip files or `.env` into images. Rationale: it supports repeatable local demos without committing restricted data. Human approval is not required because it preserves the project privacy boundary.
- 2026-09-21 — `demo-check` will fail closed when required local services or permitted artifacts are absent, rather than reporting success from a partial static check. Rationale: the command is a pre-demo guard, not a mock.

## Outcomes and retrospective

Phase 8 is complete.

Startup evidence:

- docker compose build used a 11.86 KB root build context after .dockerignore excluded .env and data.
- docker compose up -d with POSTGRES_PORT=55432 completed PostgreSQL health check, migration, idempotent loader backfill (120 fare contexts), backend health, and frontend startup.
- scripts/demo_check.py passed all seven checks against the live stack. Its unreachable-backend drill reported two failures and exited 1, proving it fails closed.

Final command-surface evidence:

- mingw32-make PYTHON=.venv/Scripts/python.exe test e2e demo-check exited 0.
- It reported 49 Python tests, 7 frontend tests, a successful production Vite build, 5 mobile Chromium E2E scenarios, and DEMO READY.
- Current PostgreSQL benchmark (50 iterations) measured p50 52.040 ms and p95 55.952 ms, below the 750 ms threshold.
- The live no-key recommendation request returned restaurant_source=fallback_fixture, five restaurants, warnings, and the deterministic template; this exercises both Places and Routes fallback without using any provider credential.
- PowerShell safety scan with IncludeWorkingTree passed 111 non-ignored candidate files. The normal tracked-file scan reports zero files because the repository has not yet received an initial commit. This is an honest limitation: no commit/push was created because the user did not authorize it.

Definition-of-Done audit:

| Requirement | Evidence |
| --- | --- |
| Phases 0–8 completed | ROADMAP status and archived plans under docs/exec-plans/completed/ |
| Rebuild and leakage-safe evaluation | Existing Phase 1–3 artifacts/evaluation evidence; README documents raw-to-serving commands and Train-only fare aggregation |
| New-local-environment startup | README prerequisite distinction; tested Compose migration/loader startup with read-only generated artifacts |
| Full/light/cold and failure resilience | Five Playwright scenarios, no-key live fallback drill, provider unit tests, deterministic LLM-disabled template |
| Demo/non-official communication | Existing UI tests plus README/demo script; fare API label says it is not an official quote |
| No prohibited Git content | Candidate-tree scan passed; generated/raw data and secrets are ignored; zero tracked files caveat recorded |
| Two-minute script and guard | README section and passing demo-check |

The remaining external product choices (real Google billing/key, runtime LLM provider, authorized brand assets, deployment) remain intentionally unimplemented and are explicitly outside the demo scope.

## Context and orientation

Startup surfaces are `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `Makefile`, `.env.example`, `README.md`, and `scripts/check_tracking.ps1`. The generated artifacts are ignored under `data/features/phase3_taipei/`; they are produced from local raw data by the documented pipeline and must not be committed.

The final Definition of Done in `docs/PROJECT_SPEC.md` §20 requires all phases, reproducible artifacts, truthful evaluation claims, a startup path, persona/failure completion, five E2E scenarios, non-official UI labels, privacy-safe Git contents, a two-minute script, and an automated pre-demo check.

## Scope

In scope: Docker Compose initialization, readiness checks, E2E completion, safety scanning, README and demo script, and final evidence.

Out of scope: deployment, paid Google/LLM use, public release, official yoxi assets, replacing deterministic ranking, or committing generated/private data.

## Plan of work

First make startup truthful: package application code without data, use one-shot migration and loader services, and bind only generated serving artifacts read-only. Then add a fail-closed readiness program and wire `make demo-check` to it. Extend browser evidence to all five required scenarios, including explicit provider and LLM template degradation. Finally update the README for a novice, execute the full acceptance suite, scan the candidate tree for prohibited content, and compare evidence against every Definition-of-Done bullet.

## Milestones

### Milestone 1 — Repeatable local startup

Compose migrates then loads an existing permitted artifact set before the backend starts; no image contains raw data or secrets.

### Milestone 2 — Demonstration guardrails

A single readiness command verifies artifact shape, fallback inventory, DB/API/frontend availability, and required non-secret configuration.

### Milestone 3 — Complete presentation evidence

Five E2E scenarios and provider/LLM failure drills prove that the demo remains understandable under expected failures.

### Milestone 4 — Definition-of-Done audit

README, two-minute script, safety scan, command outputs, limitations, and each §20 requirement have specific evidence.

## Concrete commands and expected observations

- `docker compose up --build` — PostgreSQL becomes healthy; migrator and loader finish successfully before backend/frontend serve.
- `python scripts/demo_check.py` — reports each required local check and exits nonzero for any missing dependency.
- `.\\.venv\\Scripts\\python.exe -m pytest` — backend and pipeline tests pass.
- `npm --prefix frontend run test:run`, `build`, and `e2e -- --workers=1 --reporter=line` — frontend test, build, and five E2E scenarios pass.
- `powershell -File scripts/check_tracking.ps1` plus candidate-file content scan — no prohibited release content is found.

## Validation and acceptance

The startup instructions do not claim a clean clone can operate without the user-supplied raw data and generated local artifacts. Every UI price and confirmation remains marked as historical estimate/demo. Real provider credentials remain optional and no-key fallback works. The readiness guard verifies services rather than assuming port defaults.

## Idempotence and recovery

Migrations are forward-only. Loader reruns are no-ops for the same model release except safe fare-stat backfill. A failed one-shot init can be rerun after fixing its reported prerequisite. Docker volumes are retained by default; removing a volume is documented as an explicit recovery action only.

## Interfaces and artifacts

Compose will expose frontend on 5173 and backend on 8000 by default, with configurable host ports. `scripts/demo_check.py` will use only health endpoints and local aggregate artifact metadata. The final README will list both GNU Make and direct Windows PowerShell equivalents.

## Handoff

Completed and ready to archive. No further implementation is required for the approved Taipei Demo scope. If the user later authorizes a commit, rerun scripts/check_tracking.ps1 -IncludeWorkingTree immediately before staging.

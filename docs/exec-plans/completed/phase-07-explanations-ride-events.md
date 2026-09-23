# Phase 7: inspectable explanation, simulated ride, and idempotent feedback

## Purpose and observable outcome

After a user opens a restaurant recommendation, the demo shows a short, truthful explanation, a clearly non-official historical fare-range estimate, and a simulated ride confirmation. The backend records recommendation impressions and the three later user actions exactly once per request/place/action, without storing a real rider identifier or trip history.

## Progress

- 2026-09-20T18:15:10Z — In progress: Phase 6 archived with API-backed and fallback mobile flow evidence.
- 2026-09-20T23:42:00Z — Completed Milestone 1: generated `data/features/phase3_taipei/ride/fare_estimates.json` from 451,618 model-eligible Train rows. The artifact contains 120 p25/p75 aggregate contexts and no trip rows or rider IDs.
- 2026-09-20T23:50:00Z — Completed Milestone 2: added forward migration 20260920_04, fare-stat loader support, deterministic template, `POST /api/v1/ride/estimate`, and `POST /api/v1/feedback`.
- 2026-09-20T23:57:00Z — Corrected two PostgreSQL transaction findings: recommendation items now flush before same-transaction lookup; feedback uses database `ON CONFLICT DO NOTHING` rather than application-memory checking.
- 2026-09-21T00:00:37Z — Completed Milestones 3–4: frontend shows historical-estimate disclaimer or honest unavailability, records best-effort safe events, and mobile E2E covers template/fare fallback. Full regression passed.

## Surprises and discoveries

- The current serving artifacts contain salted profile fare means but not the distance-bin/period/region p25–p75 distribution required for an honest historical fare estimate. A new aggregate-only artifact is therefore required; a profile mean is not an adequate substitute.
- D-001 and D-009 already require deterministic ranking and a template fallback, so no runtime LLM provider should be introduced while LLM credentials and policy are undecided.
- The session factory intentionally sets `autoflush=False`. PostgreSQL verification showed that child recommendation items require an explicit flush before a same-transaction estimate lookup.
- Checking for a previous event only in the ORM session is insufficient for retries within one transaction or concurrent requests. The database unique constraint plus dialect-native conflict-safe insert is the actual idempotency boundary.

## Decision log

- 2026-09-20 — Use deterministic structured-evidence templates as the shipped explanation path. Rationale: LLM provider/model remains undecided, templates satisfy D-001 and keep ranking and availability independent. Human approval is not required because this preserves accepted policy.
- 2026-09-20 — Derive fare estimates only from Train split aggregate distributions, with progressively coarser fallback bins when sample counts are insufficient. Rationale: it implements PROJECT_SPEC §14.5 without exposing trips or silently using future data. Human approval is not required because it is the specified first-version rule.

## Outcomes and retrospective

Phase 7 is complete. The fare artifact is Train-only and aggregate-only; it records 451,618 accepted rows and 120 contexts. The explanation function accepts only period and already-computed personal-mobility availability, produces a fixed Chinese sentence below 60 characters, and has no LLM credential or raw-history input.

The migration was applied to local PostgreSQL at port 55432. Rerunning `scripts/load_db.py` safely backfilled 120 fare rows into the existing release. A real PostgreSQL transaction returned five restaurants, a non-null historical fare estimate carrying the non-official label, and feedback results `recorded=True` then `recorded=False` for a duplicate ride action.

Final automated evidence:

- `.\\.venv\\Scripts\\python.exe -m pytest` — 49 passed (15 third-party deprecation warnings).
- `npm --prefix frontend run test:run` — 2 files, 7 tests passed.
- `npm --prefix frontend run build` — TypeScript check and Vite production build passed.
- `npm --prefix frontend run e2e -- --workers=1 --reporter=line` — 4 mobile Chromium flows passed in 10.9 seconds.

## Context and orientation

The serving API is in `backend/app/recommendation.py`, transport schemas in `backend/app/schemas.py`, and current tables in `backend/app/models.py`. Alembic migrations live in `backend/migrations/versions/`. Phase 6 frontend state and API client are under `frontend/src/`.

The system ranks before explanation: an explanation receives only the safe score breakdown and evidence that the recommendation already computed. It must never receive a raw rider ID or complete travel history. A ride confirmation is a visual demo only, not dispatch, payment, or an official yoxi fare.

## Scope

In scope: Train-only fare aggregate, deterministic explanation template, ride estimate and feedback APIs, idempotent persistence, client wiring, tests, and E2E.

Out of scope: a paid/runtime LLM provider, real dispatch, payment, login, restaurant booking, raw-trip persistence, official pricing, and changing ranking/provider policy.

## Plan of work

First inspect the cleaned Train artifact and produce a versioned, aggregate-only fare table grouped by distance bin, period, and region. Then add the minimal serving tables and API contracts with migrations so request, item, and feedback writes are transaction-safe and retry-safe. Add a deterministic explanation formatter that consumes only structured evidence, and make recommendation success independent of formatter failure. Finally wire the frontend to emit events and display the estimate/confirmation wording, then prove all paths in backend and browser tests.

## Milestones

### Milestone 1 — Safe fare and explanation inputs

A reproducible Train-only aggregate contains p25/p75 fare ranges and sample counts, and deterministic templates render within 60 Chinese characters from whitelisted evidence.

### Milestone 2 — Persistent API contracts

Ride estimate and feedback endpoints validate input, return only safe fields, and persist idempotently through a migrated database schema.

### Milestone 3 — Observable demo loop

The mobile flow shows template explanation, historical-estimate disclaimer, simulated ride confirmation, and sends inspectable events without blocking the experience.

### Milestone 4 — Acceptance evidence

Unit/API tests, a PostgreSQL migration/load check, and Playwright flows cover LLM-disabled template, route/fare fallback, idempotent feedback, and the full demo loop.

## Concrete commands and expected observations

- `.\\.venv\\Scripts\\python.exe -m pytest` — backend and pipeline tests pass.
- `npm --prefix frontend run test:run` — frontend tests pass.
- `npm --prefix frontend run build` — TypeScript and production bundle pass.
- `npm --prefix frontend run e2e -- --workers=1 --reporter=line` — browser scenarios pass at mobile viewport.
- `docker compose up -d postgres` followed by migration/load commands — PostgreSQL accepts new tables and idempotent writes.

## Validation and acceptance

The explanation is at most 60 Chinese characters, excludes invented taste/emotion/company claims, and is stable for identical evidence. The fare estimate identifies its historical/estimated basis and never says it is an official quote. Four feedback actions are accepted; retries create no duplicates. No raw rider ID, secret, raw trip, restricted Places response, or LLM prompt reaches the browser or repository.

## Idempotence and recovery

Fare aggregation overwrites only its own derived artifact atomically. Migrations are forward-only. Feedback retries reuse an idempotency key derived from request id, place key, and action; unique constraints make repeats no-ops. If an optional call fails, the UI stays usable and records a local warning rather than fabricating success.

## Interfaces and artifacts

New aggregate output will live below `data/features/phase3_taipei/` and be ignored when generated. Backend APIs will add `POST /api/v1/ride/estimate` and `POST /api/v1/feedback`; both use the existing uniform error body. The frontend sends only a recommendation request ID, synthetic place key, safe location/time context, and action.

## Handoff

Completed and ready to archive. The next action is to create the Phase 8 ExecPlan, audit the Definition of Done item by item, then complete README, two-minute script, failure drills, secret/raw-data scans, and demo readiness checks.

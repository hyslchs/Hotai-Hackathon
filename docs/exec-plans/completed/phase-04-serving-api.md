# Phase 4: deterministic Taipei recommendation API backed by versioned data

## Purpose and observable outcome

Turn the completed Taipei Demo artifacts into a local API that accepts a safe demo alias, location, and time and returns the same mock Top 5 restaurants with inspectable score evidence every time. A reviewer can start PostgreSQL, apply an Alembic migration, load one traceable model version, call health, rider, profile, and recommendation endpoints, and see a safe unified error when a dependency is unavailable. This phase does not contact Google, Routes, LLM, or any paid service.

## Progress

- 2026-09-20T16:44:48Z — In progress: Phase 3 is archived and D-009 fixes the Taipei serving model to A+C (A=0.30, C=0.70); B is disabled.
- 2026-09-20T17:02:00Z — Completed Milestone 1: SQLAlchemy 2.0.36 and Alembic 1.14.0 installed; initial migration passed fresh SQLite upgrade, downgrade, and upgrade validation.
- 2026-09-20T17:02:00Z — Completed Milestone 2 core: versioned loader validates the v2 report hash and D-009 A+C selection, then imports only aggregate/salted fields. Fresh SQLite load wrote 102 areas, 1,020 area-period statistics, and 41,702 profiles; a second load returned already_loaded.
- 2026-09-20T17:12:00Z — Completed Milestones 3–4 core: synthetic deterministic Top 5 service and GET demo-riders/profile plus POST recommendations endpoints work against a versioned database. API tests cover stable ordering, cold C/B unavailability, privacy, and offset-time validation.
- 2026-09-20T17:12:00Z — Schema completion: migration 20260920_02 added rider_area_stats and rider_neighbors. Full fresh SQLite load imported 94,033 salted rider-area rows and 570,700 salted neighbor rows, in addition to the earlier aggregate/profile rows.
- 2026-09-20T17:28:00Z — Completed acceptance: PostgreSQL 16 migration, full load, no-op reload, HTTP Top 5, and 50-request p95 all passed. p50=13.715 ms and p95=18.290 ms. Full make test passed 34 Python tests plus frontend tests/build; source privacy scan was clean.

## Surprises and discoveries

- Existing backend has only FastAPI health endpoints and direct psycopg readiness. It has no ORM, migration directory, loader, or recommendation route.
- The current database image is PostgreSQL 16. Phase 4 may use it locally but tests must not depend on a previously populated volume.
- Phase 3 report hash is 2b8984f3b7ee34e749370f7abba0fa13d79d1c2d618eb03afb226cbcc87d2b76. The selected model is area_a_plus_c; Test HitRate@5 is 0.4828 versus 0.3863 for Origin-Period Popularity.
- The report hash is calculated before the report_hash field is added. The loader initially rejected a valid report by hashing the full JSON; it now removes only that self-referential field before verification, matching the evaluator exactly.
- Full neighbor import takes materially longer than profiles (570,700 rows). It completed correctly in a transaction; later scalability work may use batching, but must not silently drop this versioned data.

## Decision log

- 2026-09-20 — D-009 is binding: store and serve A+C evidence only; B is explicitly unavailable, not a zero score. No new approval required because the user delegated implementation and review authority to the agent.
- 2026-09-20 — Use synthetic, repository-owned restaurant fixtures in this phase. Phase 5 alone may add an external provider adapter after an up-to-date policy review.
- Pending — Record any change to the persistence format or API contract in docs/DECISIONS.md before accepting it.

## Outcomes and retrospective

Completed. Alembic revisions 20260920_01 through 20260920_03 were applied to fresh PostgreSQL 16. The full safe import wrote 102 areas, 1,020 area-period rows, 41,702 profiles, 94,033 rider-area rows, and 570,700 neighbor rows; a repeat was a no-op. PostgreSQL caught and led to fixes for parent-before-child flush ordering and 70-character prefixed salted keys. Actual API Top 5 returned 200; 50-request p50/p95 was 13.715/18.290 ms. Full make test passed 34 Python tests plus frontend tests/build; source privacy scan passed. Scope remains Taipei Demo only and B stays disabled.

## Context and orientation

Relevant sources are backend/app/main.py, backend/app/config.py, backend/app/health.py, backend/tests, docker-compose.yml, docs/PROJECT_SPEC.md sections 13, 14, 17, 18.3, docs/ARCHITECTURE.md, and D-009. Phase 3 artifacts reside under ignored data/features/phase3_taipei. The backend must consume a named model version and may never fit ranking or read raw CSV at request time.

In plain language, a migration is a versioned database-change script. A loader is the controlled import that copies safe aggregate outputs into database tables. A repository is the small layer that reads and writes database rows so HTTP route code stays simple.

## Scope

In scope: Alembic schema; versioned loader; aliases that map only to salted rider keys; deterministic A+C area ranking; mock Top 5 provider; health/readiness artifact checks; profile and rider listing endpoints; unified errors; request/item audit rows without raw IDs; tests and a local p95 benchmark below 750 ms.

Out of scope: Google Places or Routes calls, restaurant photos, LLM explanation generation, real rider identity mapping, deployment, browser E2E, ride estimates, feedback events, all-city claims, and re-enabling B.

## Plan of work

First make persistence explicit, because an API cannot honestly claim which model it served if its source rows are unversioned. Then build the loader with atomic per-model-version behavior and prove repeat loads do not duplicate rows. Next isolate ranking from HTTP and database code so fixed inputs can be tested as ordinary functions. Add API validation and error handling around that core, using only synthetic restaurants. Finally run the local database integration suite and measure latency with a documented fixed request; optional-provider availability must never affect readiness.

## Milestones

### Milestone 1 — Versioned serving schema and migration

Create the minimum tables and indexes required by PROJECT_SPEC section 13: areas, area_period_stats, rider_profiles, rider_area_stats, rider_neighbors, recommendation_requests, and recommendation_items. Every serving row has model_version. Alembic upgrade from an empty PostgreSQL database succeeds; downgrade and fresh upgrade are documented and tested.

### Milestone 2 — Safe and idempotent artifact loader

Implement pipeline/loading or scripts/load_db.py. It validates artifact hashes and D-009-compatible model metadata before importing only aggregate or salted fields. A repeated load of the same model version changes no row counts; a failed load rolls back its transaction. It never writes raw rider_id, trip_id, or salt.

### Milestone 3 — Pure recommendation service and fallback provider

Create typed repositories and a pure service that resolves a demo alias, maps a location to a verified area or deterministic fallback, ranks areas with A+C and stable ties, and blends the selected area with five synthetic restaurants. Missing C is unavailable and weights are renormalized. Identical inputs return identical ordered scores and model_version.

### Milestone 4 — HTTP contracts and operational behavior

Implement GET /api/v1/demo/riders, GET /api/v1/demo/riders/{alias}/profile, and POST /api/v1/recommendations. Validate timezone-aware datetime and Taipei coordinates; return a shared Chinese-safe error shape with request_id and retryable. Readiness checks database and required model metadata but not optional providers.

### Milestone 5 — Acceptance evidence

Run unit, API, loader, migration, idempotence, privacy, and p95 benchmark tests. Record exact commands, results, environment caveats, and the first next action. Only then set Needs review; user-authorized agent review may close the phase if all evidence is present.

## Concrete commands and expected observations

From F:/Project/Hotai-Hackathon:

- mingw32-make PYTHON=.venv/Scripts/python.exe test — exit 0 with backend, pipeline, and frontend tests.
- docker compose up -d postgres — PostgreSQL health becomes healthy without exposing credentials in reports.
- .venv/Scripts/python.exe -m alembic upgrade head — creates the versioned schema from an empty database.
- mingw32-make PYTHON=.venv/Scripts/python.exe load-db — imports the named Phase 3 model once and reports only safe counts and hashes.
- .venv/Scripts/python.exe scripts/benchmark_recommendations.py — reports fixed-request p50/p95, with p95 below 750 ms in the documented local environment.
- mingw32-make safety-check — passes; because this local repository initially has zero tracked files, also run explicit source and generated-output privacy scans.

## Validation and acceptance

Acceptance requires migration upgrade on a fresh database; safe repeat loading; deterministic equal responses for the same request; exactly five ranked synthetic restaurants on normal and fallback locations; B represented as unavailable; no raw identifiers in responses/logs/artifacts; 422 validation errors and safe 503 dependency errors; unit and integration tests passing; p95 under 750 ms; and documented proof that optional-provider failure does not make health fail.

## Idempotence and recovery

Use a transaction keyed by model_version. Rerunning a successful loader must be a no-op. If validation or an insert fails, roll back the transaction and keep the prior model version intact. Do not use destructive volume removal automatically. For an explicitly requested local reset only, document docker compose down -v and alembic upgrade head; never run that reset as routine testing.

## Interfaces and artifacts

The recommendation request contains rider_alias, a named latitude/longitude location, and an ISO 8601 offset datetime. The response contains request_id, model_version, personalization_level, restaurant_source set to demo_fixture or fallback_fixture, five restaurants, normalized score_breakdown, structured evidence, and warnings. It does not contain raw IDs, salts, provider responses, or a claim of official yoxi pricing. Migrations live in backend/migrations. Loader reports live in ignored data/reports or concise test output.

## Handoff

Fresh-session first action: read AGENTS.md, ROADMAP.md, this file, PROJECT_SPEC sections 13–14 and 18.3, ARCHITECTURE.md, and D-009; then run git status --short --branch --ignored. The first incomplete action is Milestone 1: inspect existing dependency lock boundaries and implement the initial versioned migration without changing unrelated frontend behavior.

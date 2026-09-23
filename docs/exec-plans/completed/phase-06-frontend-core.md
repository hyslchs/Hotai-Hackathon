# Phase 6: mobile-first API-backed demo flow

## Purpose and observable outcome

Full, light, and cold personas can select a location, receive a Top 5, open detail and technical evidence, and reach a clearly simulated ride confirmation at 390×844. The frontend prefers the documented API and visibly falls back to local synthetic data.

## Progress

- 2026-09-20T17:52:00Z — In progress: Phase 3 supplied an accessible mock state machine and mobile visual smoke check.
- 2026-09-20T17:58:00Z — Completed Milestone 1: API client normalizes safe backend data; unset URL, fetch failure, and 503 all retain marked local fallback. Frontend tests now cover API success and 503 fallback.
- 2026-09-20T17:58:00Z — Mobile evidence: Edge generated a 390×844 screenshot and DOM contained the main title, non-official Demo label, and launch control. The Windows image-inspection helper failed despite the 61 KB screenshot existing, so this is weaker than a human-visible screenshot inspection.
- 2026-09-20T18:04:00Z — Completed Milestone 2: the app requests the documented POST endpoint when configured, preserves local synthetic fallback on unavailable API, and announces full, light, cold, fallback, and service-outage states. CORS now permits the frontend POST. The map pin has a distinct accessible name from the location selector.
- 2026-09-20T18:11:00Z — Completed Milestone 3: Playwright mobile Chromium E2E covers full recommendation-to-simulated-ride, cold-start explanation gaps, Taipei fallback, and outage recovery; 4/4 passed.
- 2026-09-20T18:15:10Z — Completed phase regression: 45 Python tests, 6 frontend tests, frontend production build, and 4 E2E scenarios passed.

## Surprises and discoveries

- Existing mock labels must remain visible when fallback data is used.
- Playwright 1.52 could not discover tests under Node 24 in this environment. Updating the development-only runner to the current stable release fixed discovery; Chromium is explicitly selected because the iPhone device descriptor otherwise selects uninstalled WebKit.
- This managed Windows environment denies Vite binding to 127.0.0.1:4173 but permits 0.0.0.0:5173. The checked-in E2E server uses the verified binding and port.

## Decision log

- 2026-09-20 — Local fallback remains available when backend is unavailable.
- 2026-09-20 — Mobile browser coverage uses Chromium with iPhone 13 viewport/touch emulation, rather than installing WebKit solely for a test descriptor. No human approval required; it matches the installed test browser and preserves mobile interaction coverage.

## Outcomes and retrospective

The mobile-first demo now has an API-backed path and a deterministic, visibly marked local fallback. It makes no official-brand or real-time claim when operating on synthetic data. The API browser boundary is usable because CORS allows POST only in addition to its existing GET allowance.

Acceptance evidence:

- `.\\.venv\\Scripts\\python.exe -m pytest` — 45 passed (15 third-party deprecation warnings).
- `npm --prefix frontend run test:run` — 2 files, 6 tests passed.
- `npm --prefix frontend run build` — TypeScript check and Vite production build passed.
- `npm --prefix frontend run e2e -- --workers=1 --reporter=line` — 4 mobile Chromium scenarios passed in 10.8 seconds.

The final browser test output contains a benign Node colour-environment warning. This environment does not provide `make` in PowerShell, so the documented Makefile commands were validated through their explicit underlying commands.

## Context and orientation

Relevant paths are frontend/src/App.tsx, frontend/src/app/demoMachine.ts, frontend/src/mocks/taipeiDemo.ts, and the Phase 4 recommendation contract.

## Scope

API client, mobile state flow, accessibility, visual checks, and E2E are in scope. Provider-policy changes, ride estimates, feedback events, and deployment are out of scope.

## Plan of work

Normalize API and fallback outputs first, then connect state transitions without exposing internal reasoning. Finally validate full, cold, fallback, and backend-failure browser flows.

## Milestones

### Milestone 1 — API/fallback contract

One result component renders either safe API output or marked local fallback.

### Milestone 2 — Accessible mobile flow

All personas complete select, recommend, detail, and simulated ride flow with retry/error.

### Milestone 3 — Browser acceptance

Mobile visual and E2E scenarios pass.

## Concrete commands and expected observations

- `.\\.venv\\Scripts\\python.exe -m pytest` — 45 Python tests pass.
- `npm --prefix frontend run test:run` — 6 frontend tests pass.
- `npm --prefix frontend run build` — production frontend build passes.
- `npm --prefix frontend run e2e -- --workers=1 --reporter=line` — four mobile Chromium scenarios pass.

## Validation and acceptance

Every persona completes; fallback and 503 are understandable; lists/markers synchronize; keyboard and announcements work; no keys or raw IDs reach the browser. The agent review used the passing component, API-contract, and browser scenarios as the phase review evidence.

## Idempotence and recovery

Repeat requests are safe. Backend failure uses local synthetic fallback.

## Interfaces and artifacts

The frontend reads VITE_BACKEND_URL and only safe API response fields.

## Handoff

Completed and ready to archive. The next action is to author the Phase 7 ExecPlan from the observed Phase 6 state; do not change provider-policy behavior while adding explanations, ride estimates, and events.

# Phase 9 — Inspectable live calculation and route map

## Purpose and observable outcome

Turn the existing Taipei Demo from a static-map presentation into an inspectable recommendation flow. A reviewer selects a demo persona, location, and time; can inspect deterministic area-ranking evidence from the existing Train-only artifacts through the API; sees restaurant suggestions and travel estimates in plain language; and can select a restaurant to draw its Google Routes polyline on an interactive Google map. The consumer screen does not show internal scores, weights, or stage logs under D-013.

Without Google credentials, the same flow must remain usable with the repository-owned fallback restaurants and an explicit static map. The product must never claim a suggested Google route is a historical vehicle trajectory, retain Google Places content across requests, expose server API keys, or use raw rider data in the browser.

## Progress

- [2026-09-21T00:00:00Z] Completed — inspected current artifacts, backend, frontend, provider adapters, environment wiring, and acceptance tests.
- [2026-09-21T00:00:00Z] Completed — user approved D-011 and Phase 9 scope.
- [2026-09-21T03:32:29Z] Completed — added aggregate-only profile fields, versioned serving configuration, pure A+C ranking, contextual restaurant scoring, and idempotent loader backfill behavior.
- [2026-09-21T03:32:29Z] Completed — added bounded Route Matrix and selected-route polyline adapters with mocked FieldMask, ordering, failure, and fallback tests.
- [2026-09-21T03:32:29Z] Completed — exposed trace-safe area/candidate/route stage records and the nullable suggested-route polyline in backward-compatible API responses.
- [2026-09-21T03:32:29Z] Completed — replaced the CSS-only map with a dynamic Google Maps wrapper, map-click origin selection, marker/list selection synchronization, selected-route drawing, and an explicit static fallback.
- [2026-09-22T15:18:37Z] Completed — added a serving-time persona distance budget, proximity tie-break, and round-robin restaurant shortlist so distant areas and single-area Top 5 concentration are no longer the default Demo behavior.
- [2026-09-22T15:18:37Z] Completed — keyless verification after D-012: 58 backend/pipeline tests, 7 frontend unit tests, frontend production build, 5 mobile E2E scenarios, `scripts/demo_check.py`, and tracking safety check all passed. Live Google-provider acceptance remains conditional on user-managed credentials and billing.
- [2026-09-23] Completed — D-013 consumer copy pass across home, input, loading, results, detail, ride preview, error, map, and document metadata. Internal scores/stages were removed from the consumer screen while the API trace remained available. Frontend unit tests (7), production build, five mobile E2E flows against a fresh Vite server, and focused backend API tests (6) passed.
- [2026-09-23T10:48:34Z] Completed — user-approved D-014 detail-view extension: added clearly labelled simulated text reviews with one-to-five-star scores and a session-only demo rating picker. `npm --prefix frontend run build` passed after the changes; test suites were not run.

## Surprises and discoveries

- The repository already contains real local Taipei artifacts: a 200,000-point Train fit, 102 verified Taipei areas, and locked A+C evaluation evidence at `data/features/phase3_taipei/`. The selected model is `area_a_plus_c`; B is disabled under D-009.
- The current backend loads only a subset of profile columns needed to reproduce C. `p25_distance_km`, `morning_ratio`, and `afternoon_ratio` exist in the Parquet artifact but not in the serving model.
- `backend/app/recommendation.py` currently selects the highest A area, keeps at most five provider results, and applies a provider-index decrement. That is not the complete locked A+C area-ranking plus documented restaurant-ranking contract.
- `backend/app/providers.py` requests only duration and distance from `computeRoutes`; it cannot render a route without requesting `routes.polyline.encodedPolyline`.
- The frontend has no Maps JavaScript integration. Its `MapCanvas` is CSS-only and its markers do not use coordinates.
- No Google Maps, Places, or Routes keys are currently configured. Docker Desktop is not running on this host, so Compose acceptance cannot yet be run locally.
- `npm --prefix frontend run e2e -- --workers=1 --reporter=line` initially found an ambiguous accessible label: the static map's current-position marker matched the location selector. Renaming the marker to `地圖定位標記` restored the five mobile E2E scenarios.
- Keyless verification now passes: 54 Python tests, 7 frontend unit tests, frontend production build, and 5 mobile E2E scenarios. `scripts/demo_check.py` correctly stops at backend/database readiness because Docker is not running; its artifact, fallback and frontend checks pass.
- Restaurant details now include sample review text and an optional demo-only rating interaction under D-014. Review copy and star scores are illustrative and must never be read as actual customer feedback.

## Decision log

- 2026-09-21 — D-011 accepted by the user. Phase 9 will use Google Maps JavaScript API for the live map, but preserve a static fallback for missing or unusable browser keys.
- 2026-09-21 — Serving will not refit HDBSCAN or read raw trips on each request. It will use the loaded Train-only aggregate artifacts and profile data, which is the normal and reproducible boundary between offline training and online inference.
- 2026-09-21 — Use `computeRouteMatrix` only for a bounded restaurant shortlist, then call `computeRoutes` with an encoded-polyline FieldMask only when the viewer selects a restaurant. This limits cost and makes the displayed path attributable to the selected result.
- 2026-09-21 — A calculation trace will report factual completed stages, counts, source labels, and durations. It will not simulate model chain-of-thought or individual historical trips. Human approval not required; this follows the existing explanation and privacy constraints.
- 2026-09-22 — The user approved D-012: serving adds a bounded persona distance budget and 20% proximity fit without refitting the offline model. Live restaurant route candidates are selected round-robin across ranked areas, targeting no more than two per area before the minimum Top 5 fill fallback.
- 2026-09-23 — The user requested D-013: the consumer flow now shows short plain-language choices and reasons. The API still carries the same calculation evidence for reviewer inspection. Synthetic restaurant, static-map, fare, and simulated-ride disclosures remain visible where they affect decisions.
- 2026-09-23 — The user requested D-014: restaurant details show explicitly simulated text reviews with one-to-five-star ratings and an optional session-only demo rating. This adds no review API, persistence, or restaurant-photo source.
- 2026-09-21 — The restaurant layer uses the specification's 0.60 AreaScore + 0.20 D + 0.20 POIQuality formula. Within D, the deterministic travel-time curve is full score up to the rider's median duration, decreases to 0.65 by 1.5× median, then decays; RideWorthiness is low below 1 km, high through the rider-supported 2–10 km range, then decays after p90. Missing public POI fields reweight remaining POI components. This does not alter the accepted offline A+C area model. Human approval not required because it implements the prescribed component behavior and has explicit response evidence.

## Outcomes and retrospective

Pending. Complete this section before moving this plan to `docs/exec-plans/completed/`.

## Context and orientation

The offline pipeline in `pipeline/` produced `data/features/phase3_taipei/` from authorized local data. `pipeline/loading/serving.py` transfers only salted/aggregate data to PostgreSQL. `backend/app/recommendation.py` currently orchestrates selection, Places, Routes estimates, ride estimates, and feedback. `backend/app/providers.py` contains the current opt-in Google adapters. `frontend/src/App.tsx` is a mobile-first, single-page state machine with an API client at `frontend/src/api/recommendations.ts`.

The locked offline model is A+C: A is `AreaPeriodStat.attraction_score`; C combines distance fit, time habit, weekday fit, and rider-area affinity. The runtime must use the locked 0.30 A / 0.70 C weights for supported riders and reweight to A only for cold or unavailable C. All score components are normalized to 0–1. The final restaurant score is 0.60 AreaScore + 0.20 contextual D + 0.20 POIQuality, with stable tie-breaking.

Google Places and Routes keys remain server-only. The Maps browser key is intentionally visible to the browser but must use HTTP-referrer restrictions and be exposed only as a `VITE_` variable. Google Places result fields are ephemeral; only place IDs may be retained. The app must retain the current legal fallback and must label its source.

## Scope

In scope:

- Align serving A+C ranking with the locked artifact and extend loaded profile fields.
- Search bounded Top areas for restaurant candidates, calculate documented restaurant components, and retain only current-request provider data.
- Add Route Matrix estimates and selected-route encoded polylines.
- Add trace-safe API fields, interactive Google Maps rendering, map click origin selection, time selection, marker/list synchronization, and a static fallback.
- Under D-014, show clearly labelled simulated text reviews and a one-to-five-star rating interaction that stays in the current page only.
- Add focused backend, frontend, E2E, configuration, and documentation coverage.

Out of scope:

- Refitting models, changing D-009 weights, all-city generalization, live learning, raw GPS trajectory display, actual yoxi ordering/payment, LLM ranking, deployment, Google billing setup, or use of official brand assets.

## Plan of work

First, isolate pure serving ranking functions and load the missing safe profile values so the online score can be compared against the established A+C behavior. Add a migration and loader update before using the values; loading the same model release must remain idempotent.

Second, evolve provider adapters rather than placing HTTP calls in ranking code. Places retrieves bounded and deduplicated current-request candidates. Routes first supplies a matrix for a bounded shortlist, then full route details only on selection. Every provider operation preserves the existing timeout, one retry, and fallback semantics.

Third, extend API contracts with trace-safe facts: candidate counts, selected areas, component values, source labels, durations, and selected-route polyline. Keep existing response fields so the legacy fallback can render during frontend migration.

Fourth, introduce a Google Maps wrapper that loads Maps JavaScript API dynamically only with `VITE_GOOGLE_MAPS_BROWSER_API_KEY`; otherwise it renders the explicit static fallback. It will display area circles, coordinate-based markers, selected marker focus, and decoded route polylines. Under D-013, the consumer UI gives a short waiting message and leaves factual stages in the API response for reviewers.

Finally, verify deterministic ranking against fixtures, provider failure modes, map fallback behavior, secret boundaries, and the live path when user credentials and Docker are available. Record every command and observation in this plan.

## Milestones

### Milestone 1 — Serving ranking matches the accepted Taipei model

Add safe profile fields, versioned model metadata, and pure runtime A+C/D/POI functions. A fixed database fixture must return stable area candidates and Top 5 scores with correct availability/reweighting. No provider is required.

### Milestone 2 — Bounded real-provider candidates and route data

Implement multi-area Places retrieval, deduplication, hard filters, route matrix estimates, and selected-route polyline retrieval. Mocked tests prove exact FieldMasks, bounded calls, fallback behavior, and no persistent provider payload.

### Milestone 3 — Trace-safe API contract

Recommendation responses include top-area evidence and calculation-stage counts/timing; ride estimates include a nullable encoded polyline and route source. Existing clients still render safe fallback responses.

### Milestone 4 — Interactive map and factual calculation record

The browser renders Google Maps when a restricted browser key is supplied; otherwise it renders the static fallback. Area circles, restaurant markers, list/marker focus, map-click origin choice, time input, source labels, and selected-route polyline work at mobile size. Consumer copy follows D-013; the calculation record remains inspectable through the API.

### Milestone 5 — Verification and handoff

All Python, frontend, build, E2E, safety, and demo checks pass in keyless mode. If credentials and Docker are available, run the live acceptance flow and record source, route, and attribution observations. Update README and this plan; stop at human review.

## Concrete commands and expected observations

Run from `F:\Project\Hotai-Hackathon`:

```powershell
.\.venv\Scripts\python.exe -m pytest
npm --prefix frontend run test:run
npm --prefix frontend run build
npm --prefix frontend run e2e -- --workers=1 --reporter=line
.\.venv\Scripts\python.exe scripts/demo_check.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_tracking.ps1
```

Expected: all commands exit 0; tests prove keyless fallback and no server keys in browser bundles. Docker-dependent commands (`docker compose up --build`, then `scripts/demo_check.py`) are deferred until Docker Desktop is running. Live Google verification is deferred until the user supplies enabled, restricted credentials; it must record `restaurant_source=google_places`, `route_source=google_routes`, and a non-empty encoded polyline without printing secrets.

## Validation and acceptance

- Fixed inputs and fixed provider fixtures yield deterministic Top areas, Top 5, components, and trace order.
- Changing persona, time, or map-selected origin changes input-dependent area scoring; no raw row is read during a request.
- Offline/default ranking retains the 20 km then 30 km rule; API serving applies the D-012 persona distance budget and returns no more than Top 10 eligible areas to Places.
- Places candidates are deduplicated, filtered, and source-labelled. Missing keys, timeout, 429, 5xx, malformed responses, and insufficient candidates fall back safely.
- Default live shortlist is round-robin across ranked areas, with a target cap of two restaurants per area and an explicit fill fallback when fewer than five provider candidates or areas are available.
- Matrix estimates are bounded and selected-route polylines are nullable, source-labelled, and never represented as historical trajectories.
- On a real map, marker and list selections stay synchronized and routes visibly follow decoded polylines. Without a valid browser key, static-map fallback and recommendations remain usable.
- Restaurant detail identifies sample reviews as simulated, displays each score from one to five stars, and explains that the visitor's demo rating is not sent or saved.
- No raw identifiers, Places response cache, server key, or unapproved brand asset enters tracked files, logs, or frontend output.

## Idempotence and recovery

The database migration only adds nullable safe serving fields and the loader backfills them when a release is already present but incomplete. Provider calls do not mutate persistent provider storage. API schema additions are optional or backward-compatible during the frontend migration. If a browser key is absent, invalid, or Maps loading fails, remove map-specific state and render the existing static fallback; do not block recommendation results. If live providers fail, retain the existing synthetic fallback and trace source.

If a migration or loader fails, preserve the existing database volume, correct the error, rerun migration then loader, and verify readiness. Do not delete volumes or reset the database as recovery.

## Interfaces and artifacts

- `POST /api/v1/recommendations` gains a `calculation` object containing model version, origin assignment summary (including serving distance budget and proximity weight), Top areas, factual stage timing/counts, and candidate sources. Restaurant items gain `context_fit`, `poi_quality`, source area, and safe ranking evidence.
- `POST /api/v1/ride/estimate` gains nullable `encoded_polyline` and `route_source`; route text calls it a suggested route.
- `backend/app/providers.py` exposes typed Places, Route Matrix, and selected-route results with explicit fallback outcomes.
- `frontend/src/api/recommendations.ts` normalizes the expanded safe fields. The map component consumes only coordinates, scores, source labels, and encoded polylines.
- `.env.example` documents `VITE_GOOGLE_MAPS_BROWSER_API_KEY`, `GOOGLE_PLACES_API_KEY`, and `GOOGLE_ROUTES_API_KEY`; Compose passes only the browser-safe key to the frontend.

## Handoff

The first incomplete action is Milestone 5: with Docker Desktop running, run `docker compose up --build`, wait for readiness, then run `scripts/demo_check.py`. If the project owner configures enabled, restricted local Maps/Places/Routes keys, perform one manual live flow and record only source labels and non-secret observations: `restaurant_source=google_places`, matrix route source, and a non-empty selected-route polyline. Never print key values or persist Places payloads. Then move the plan to `Needs review` for the user.

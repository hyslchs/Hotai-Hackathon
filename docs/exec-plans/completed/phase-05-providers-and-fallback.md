# Phase 5: policy-safe Places and Routes with a complete keyless demo

## Purpose and observable outcome

The Taipei API returns five restaurants whether provider keys exist or not. With keys, it uses a bounded Google request with only necessary fields. Without keys or after eligible provider failures, it uses repository-owned synthetic restaurants and Haversine times without interrupting the demo.

## Progress

- 2026-09-20T17:40:00Z — In progress: reviewed current Google official Nearby Search, Places policy, and Compute Routes documentation.
- 2026-09-20T17:40:00Z — Implemented adapters with explicit FieldMask, 2.5-second default timeout, deduplication, keyless Places fallback, and Routes Haversine fallback.
- 2026-09-20T17:48:00Z — Completed: mocked tests cover keyless, timeout, 429, 5xx, malformed routes, deduplication, required FieldMask, and one retry. API uses one expansion/next-area attempt then repository-owned fallback.
- 2026-09-20T17:48:00Z — Completed acceptance: D-010 records the external-provider/caching policy; full make test passed 44 Python tests and frontend test/build.

## Surprises and discoveries

- Nearby Search requires POST and an explicit FieldMask; no field mask is an error.
- Places content is not generally cacheable or storable, while Place IDs are an explicit exception. The adapter therefore does not persist provider responses.

## Decision log

- 2026-09-20 — Default to keyless fallback. Google requests occur only when a server-side key is set; no key is sent to the frontend.
- Pending — Add a durable decision record after tests demonstrate the selected policy behavior.

## Outcomes and retrospective

Completed. Provider data is request-local and is never written to serving tables. Keyless mode is the default demonstrable path; live mode has strict request bounds and safely degrades.

## Context and orientation

Relevant files are backend/app/providers.py, backend/app/recommendation.py, backend/app/config.py, PROJECT_SPEC sections 11.6–11.8, 17, and 18.3, plus the official Google documentation consulted on 2026-09-20. FieldMask means an allow-list of exactly which provider fields may return.

## Scope

In scope: Nearby Search adapter, Routes adapter, timeout/429/5xx/malformed handling, place deduplication, insufficient-result fallback, and policy-safe no-cache behavior. Out of scope: photos, long-term Google content caching, external provider calls without a configured key, deployment, and frontend E2E.

## Plan of work

Keep provider calls behind adapters so their failures cannot influence deterministic area ranking. Request only restaurant identity, location, rating, review count, price level, and current opening status. Use Routes only per shortlisted restaurant. A missing or failed provider produces a structured source/warning and deterministic fallback.

## Milestones

### Milestone 1 — Safe provider contracts

Adapters construct documented POST requests and bounded field masks. Tests inspect request payloads without using a real key.

### Milestone 2 — Failure and fallback behavior

Timeout, 429, 5xx, malformed JSON, duplicate IDs, and fewer than five results all finish through fallback.

### Milestone 3 — Integration evidence

Keyless API returns five results and marks fallback; mock successful provider results are deduplicated and route estimates use returned distance/time.

## Concrete commands and expected observations

- .venv/Scripts/python.exe -m pytest backend/tests -q — provider and API contracts pass without network access.
- mingw32-make PYTHON=.venv/Scripts/python.exe test — all project tests and frontend build pass.

## Validation and acceptance

No provider response is committed or cached. Real-key mode uses explicit fields and bounded timeout. Keyless and each failure mode return a completed recommendation with visible source/warning.

## Idempotence and recovery

Provider calls create no persistent cache. Retrying a request is safe; retryable errors fall back after one bounded attempt rather than looping.

## Interfaces and artifacts

Places source is google_places or fallback_fixture. Route evidence is google_routes or haversine_fallback. The response never includes API keys or raw provider payloads.

## Handoff

Fresh-session first action: read this plan, D-009, provider code, and official Google docs. The first incomplete action is Milestone 2 provider failure-mode tests.

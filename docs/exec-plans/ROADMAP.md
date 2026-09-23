# yoxi AI Demo execution roadmap

This roadmap decomposes `docs/PROJECT_SPEC.md` by technical dependency rather than document order. It tracks portfolio status and decision gates; implementation detail and evidence belong in the current active ExecPlan.

## Status

| Phase | User-visible or reviewable outcome | Depends on | Status | Exit |
| --- | --- | --- | --- | --- |
| 0 — Foundation and data contract | A repeatable repo starts locally and safely recognizes the supplied data contract | None | Completed | Automated acceptance, then review |
| 1 — Cleaning and quality | Raw rows reproducibly become clean/quarantine Parquet and an auditable quality report | Phase 0 | Completed | Automated acceptance and human approval |
| 2 — Geographic-area experiment | Reviewers can compare area candidates and inspect Taipei, Taichung, and Kaohsiung maps | Phase 1 approved | Completed (Taipei Demo scope) | Taipei Demo scope accepted; all-city generalization deferred |
| 3 — Features and offline evaluation | Taipei Demo features and deterministic recommendation baseline are built without leakage; full all-city comparison is deferred | Phase 2 approved | Completed (Taipei Demo scope) | Locked evaluation and agent-authorized review |
| 4 — Serving database and recommendation API | Alias, location, and time return deterministic mock Top 5 with score evidence | Phase 3 completed | Completed | PostgreSQL, API, safety, and performance acceptance |
| 5 — Places, Routes, and fallback | Real-key and no-key modes both complete restaurant retrieval safely | Phase 4 completed | Completed | D-010 policy and failure-mode acceptance |
| 6 — Frontend core flow | Full, light, and cold personas can complete the mobile recommendation flow against mocks | Phase 4; may use Phase 5 mocks | Completed | Visual and E2E review |
| 7 — Explanation, ride demo, and events | Recommendation-to-demo-ride loop works with explanations, estimates, and inspectable events | Phases 5 and 6 | Completed | E2E acceptance |
| 8 — Hardening and handoff | A clean environment can launch and demonstrate the system in two minutes, including provider failures | Phase 7 | Completed | Final Definition of Done |
| 9 — Live calculation map and trace | A reviewer can inspect data-backed area ranking, live Places candidates, route estimates, and an interactive route map | Phase 8; Google credentials required only for live verification | In progress | Human review of live and keyless demonstrations |

Phases 1–8 are complete for the original Taipei Demo scope. Phase 9 is active under D-011 to make the existing data-backed recommendation process inspectable on an interactive map. It does not reopen the locked offline evaluation, fit on request data, or authorize Google billing configuration; live verification remains conditional on user-supplied credentials.

## Phase 0 — Foundation and data contract

Establish the directory layout, pinned environments, configuration boundaries, Docker Compose, `.gitignore`, data schema, small test fixture, test runners, health skeletons, and durable documentation hooks. Preserve any existing implementation after inspecting it. The phase is successful when a new contributor can bootstrap the repository, start frontend/backend/PostgreSQL, run foundational tests, and verify that raw data and secrets are untracked. The active plan is `docs/exec-plans/active/phase-00-foundation.md`.

## Phase 1 — Cleaning and quality

Implement chunked or streaming ingestion, schema conversion, time-aware parsing, fare-range parsing, hard-invalid quarantine, soft-outlier reporting, derived fields, time split, Parquet outputs, and machine/human-readable quality reports. The implementation now reconciles all 964,991 raw rows, reports the required 452,333 / 169,934 / 342,724 split counts before model exclusions, includes the 40 trips after midnight on May 1 in Test, and produces identical reports and artifact hashes on rerun. Evidence is recorded in `docs/exec-plans/completed/phase-01-cleaning-and-quality.md`; the user approved the review gate on 2026-09-18 before Phase 2 began.

Primary risk is that observed encodings or values contradict the supplied contract. Such contradictions are reported with samples that do not expose real rider identifiers and escalated when they change a research conclusion.

## Phase 2 — Geographic-area experiment

Fit geographic-area candidates on Train coordinates only. Start with bounded 50k, 100k, and 200k stratified samples, measure runtime and peak memory, and compare the HDBSCAN parameter grid required by `PROJECT_SPEC.md` §10.3. Produce cluster/noise/size/radius/coverage metrics plus visual checks for Taipei, Taichung, and Kaohsiung. Prove that pickup and dropoff can be assigned by the same model and that validation/test assignment does not refit it.

Exit only after a human accepts a parameter set with evidence. If no candidate has reasonable scale, noise, coverage, and resource use, present H3 and DBSCAN fallback tradeoffs and stop. Do not silently substitute k-means or start recommendation features.

## Phase 3 — Features, baselines, and offline evaluation

Phase 3 is completed in docs/exec-plans/completed/phase-03-taipei-demo.md. It built the Taipei Demo slice: approved area artifact, aggregate features, deterministic recommendation baseline, fallback evidence, and locked evaluation. Settings were selected only on Validation; the complete six-model all-city comparison remains deferred until a later approved scope expansion.

The evaluation package found that A+C reliably beats Origin-Period Popularity within the Taipei Demo test, while B adds no validated benefit. D-009 records the simplest winning serving model and B disablement.

## Phase 4 — Serving database and recommendation API

Create Alembic migrations, versioned loaders, repositories, pure ranking services, demo alias mapping, health endpoints, demo-rider/profile endpoints, recommendation contract, unified error schema, and mock restaurant provider. Loading must be retryable and must never expose raw IDs. With mocked external services, a fixed request returns deterministic Top areas and Top 5 restaurants with normalized score breakdown and evidence. Integration tests pass and recommendation API p95 is below 750 ms in the documented local benchmark environment.

Do not fit models in the backend and do not use a floating `latest` artifact in place of a traceable `model_version`.

## Phase 5 — Places, Routes, and legal fallback

Implement provider adapters with explicit FieldMask, bounded timeout, at most one eligible retry with jitter, place deduplication, open-status handling, next-area search, radius expansion, and a rights-safe fallback dataset. Routes remains optional and is called only for shortlisted candidates; historical speed and Haversine × 1.30 remain the fallback.

Real-key and keyless demonstrations must both finish. Tests cover timeout, 429, 5xx, malformed responses, insufficient restaurants, and policy-safe caching. Stop if keys, billing, licensing, attribution, or changed provider policies prevent compliant testing.

## Phase 6 — Frontend core flow

Build the single mobile-first map route and bottom-sheet state machine for home, location selection, recommendation loading, results, restaurant detail, ride confirmation shell, and recoverable error. Full, light, and cold personas must work against the documented API or mocks. Lists and markers remain synchronized; fallback source, demo status, loading, keyboard focus, labels, contrast, and error announcements are understandable.

Acceptance is observed at 390×844 and a desktop centered preview with component tests and Playwright flows. Do not use an unauthorized logo or imply this is the official yoxi application.

## Phase 7 — Explanation, ride demo, and feedback

Add structured-evidence explanations with deterministic template fallback, historical fare-range estimate, explicitly simulated ride confirmation, technical score panel, and idempotent impression/click/explanation/ride events. The LLM receives neither full trip history nor real rider ID and remains optional.

The complete flow must work with LLM disabled. A reviewer can query or otherwise inspect all four event types, and every displayed fare is clearly historical estimation rather than official pricing.

## Phase 8 — Hardening and presentation handoff

Complete the required five E2E scenarios, performance measurements, deterministic demo seeds, provider outage drills, `make demo-check`, README, two-minute script, and recording checklist. Validate a clean bootstrap and scan tracked files and built frontend assets for secrets, raw data, real rider mappings, and restricted provider responses.

The project is complete only when every item in `PROJECT_SPEC.md` §20 is satisfied or an explicitly approved reduction is recorded. Deployment and public release remain separate, user-authorized actions.

## Cross-phase gates

Stop and request a decision when geographic clustering has no defensible result; the complete model fails the strong baseline; Google credentials, billing, licensing, or policy blocks testing; official brand assets or private APIs are required; deployment or paid infrastructure is proposed; or the observed data meaning conflicts with the supplied field description in a way that changes conclusions.

Unknown Google keys, brand authorization, deployment location, runtime LLM provider, and restaurant photos do not block Phases 0–4. Default to no LLM and no photos until accepted otherwise.

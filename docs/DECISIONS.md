# Decision log

This document records durable decisions that affect later phases. Do not use it as a task log. Proposed choices remain `Proposed` until the named approver accepts them.

## Status values

- `Proposed`: evidence exists but human approval is still required.
- `Accepted`: the repository should implement this choice until superseded.
- `Rejected`: considered and not selected.
- `Superseded`: replaced by a later decision whose identifier is linked.

## Accepted starting constraints

### D-001 — Deterministic ranking owns recommendation order

- Status: Accepted
- Date: 2026-09-18
- Context: The demo needs explainable, reproducible ranking and an honest offline comparison.
- Decision: A deterministic algorithm ranks areas and restaurants. An LLM may only convert supplied structured evidence into at most 60 Chinese characters. Failure or disablement uses a deterministic template.
- Consequences: Ranking tests never require an LLM; explanation failure cannot fail the recommendation request.
- Reversible: Yes, but a change would alter the research claim and requires explicit approval.

### D-002 — Time-based evaluation split

- Status: Accepted
- Date: 2026-09-18
- Context: Random splitting would leak future mobility patterns into training.
- Decision: Use the train, validation, and test windows and counts in `PROJECT_SPEC.md` §10.1. Test is run only after configuration is locked.
- Consequences: All transforms and similarity state need fit/transform separation and leakage guards.
- Reversible: No for the reported experiment without invalidating comparability.

### D-003 — One phase and one living active plan

- Status: Accepted
- Date: 2026-09-18
- Context: Detailed future plans become stale when clustering and evaluation results change the architecture.
- Decision: Keep the roadmap for all phases, but fully expand only the approved current phase in `docs/exec-plans/active/`.
- Consequences: Phase transitions include a short planning step after evidence and approvals are available.
- Reversible: Yes.

## Decision entry template

### D-NNN — Short title

- Status: Accepted | Accepted | Rejected | Superseded
- Date: YYYY-MM-DD
- Context: What forced a choice and which evidence is available?
- Options: What credible alternatives were considered?
- Decision: What exactly is chosen?
- Evidence: Commands, reports, measurements, or policy links.
- Consequences: What becomes easier, harder, or constrained?
- Reversible: Yes or no; if yes, how?
- Approval: Who approved it, or what approval is still needed?

### D-004 — Phase 0 initializes missing local Git metadata

- Status: Accepted
- Date: 2026-09-18
- Context: The requested Phase 0 safety acceptance requires a tracked-file check, but the supplied directory had no .git directory.
- Options: Leave the directory unversioned; initialize local metadata without a remote; or create remote/project configuration.
- Decision: Initialize local Git metadata only. Do not add a remote, stage files, commit, push, or change remote configuration.
- Evidence: git init succeeded; git status shows no staged or committed files; the safety script passes.
- Consequences: Git safety checks are executable locally. The first commit remains user-controlled.
- Reversible: Yes, by a user-controlled repository deletion; no deletion was performed by Phase 0.
- Approval: Review requested with the Phase 0 gate.

### D-005 — Preserve the supplied raw CSV path and broaden ignore coverage

- Status: Accepted
- Date: 2026-09-18
- Context: The supplied attachment is at data/yoxi_rawdata.csv, while the target layout expects data/raw/.
- Options: Move or rename the user file; copy it into data/raw/; or audit the existing path and ignore data-level CSV/Parquet files.
- Decision: Do not move or duplicate the raw file. scripts/data_audit.py checks RAW_DATA_PATH, then the expected data/raw/ path, then the supplied local candidate. .gitignore ignores both data/raw/ and data-level CSV/Parquet files.
- Evidence: make data-audit reports the exact header, 964991 logical rows, zero wrong-width rows, and zero Phase 0 contract rejects. git check-ignore passes for data/yoxi_rawdata.csv.
- Consequences: Phase 1 can choose a canonical ingestion path deliberately without exposing or copying raw data.
- Reversible: Yes; path selection can be changed in a later approved plan.
- Approval: Review requested before Phase 1 ingestion conventions are finalized.

### D-006 — Phase 1 uses deterministic chunked cleaning and aggregate evidence

- Status: Accepted
- Date: 2026-09-18
- Context: Phase 1 must process 964,991 supplied CSV rows without loading the whole file into memory, preserve hard-invalid diagnostics, and provide reproducible evidence for later model work.
- Options: Use Pandas as the required runtime; use Python stdlib CSV parsing with chunked PyArrow Parquet writing; or defer generated artifacts until the clustering phase.
- Decision: The current Phase 1 implementation uses Python stdlib CSV parsing, the Phase 0 contract parser, fixed-size buffers, and pinned PyArrow 18.1.0. Hard-invalid rows go to local ignored quarantine output. Initial soft-outlier thresholds and deterministic coordinate buckets remain audit rules, not model conclusions.
- Evidence: `make preprocess` exits 0 with 964991 input, 964991 clean, 0 quarantine, exact required split counts, 40 May 1 after-midnight Test rows, and soft-outlier union 1642. A second isolated run produced equal report JSON, manifest, physical hashes, and content hashes.
- Consequences: Phase 2 can consume typed local artifacts without refitting or reparsing the raw CSV; threshold and region-bucket usefulness still require later review.
- Reversible: Yes; update the active ExecPlan and record the replacement before changing the parser or output contract.
- Approval: User approved on 2026-09-18; Phase 2 is authorized with a required included-versus-excluded soft-outlier comparison.

### D-007 — Retain soft-outliers, exclude them from the first model baseline

- Status: Accepted
- Date: 2026-09-18
- Context: Phase 1 found 1,642 soft-outlier rows (about 0.17% of clean rows). They may contain valid traffic or long-distance behavior, but can distort speed, time, fare, and other derived statistics.
- Options: Delete them; treat them as ordinary rows; or retain and flag them while excluding them from the first model-fitting baseline.
- Decision: Retain soft-outliers in clean Parquet and quality reports. The first model-fitting baseline uses model_eligible=true; Phase 2 must compare geographic clustering with and without soft-outliers and report cluster count, noise ratio, and regional coverage before choosing a downstream policy.
- Evidence: Phase 1 quality report has 964,991 clean rows, 1,642 soft-outlier rows, zero hard-invalid rows, and reproducible artifacts. The user approved this conditional policy on 2026-09-18.
- Consequences: No potentially valid trip is silently deleted. The first baseline is conservative, while the sensitivity experiment shows whether coordinate-based clustering materially depends on those rows. Validation and Test rows remain observable and must not be silently removed from later reports.
- Reversible: Yes; a later decision may adopt dimension-specific eligibility after experiment evidence.
- Approval: User approved on 2026-09-18.


### D-008 — Taipei-only demo scope enters Phase 3

- Status: Accepted
- Date: 2026-09-19
- Context: Phase 2 evidence shows Taipei is sufficiently stable for the requested simple demo, while Kaohsiung remains sensitive to soft-outlier policy and all-city generalization is not yet complete.
- Options: Continue researching all-city clustering before any downstream work; or accept a scoped Taipei demo baseline while recording the all-city limitation.
- Decision: Accept Phase 2 for the Taipei Demo scope only and allow Phase 3 to start within that scope. Keep soft-outliers in clean artifacts and reports but exclude them from the first model baseline. Freeze eligible_only with HDBSCAN preview parameters 250/25/eom as the Taipei demo baseline. Provide a deterministic fallback for Taipei points that are not assigned to a cluster. Do not claim that the area model is production-ready or generalizes to Taichung and Kaohsiung.
- Evidence: The paired same-sample diagnostic found Taipei coverage changed by only +0.6155 percentage points after adding soft-outlier endpoints; the corresponding Kaohsiung change was -14.5576 percentage points. The 72-candidate Phase 2 experiment, assignment checks, maps, and aggregate reports are complete.
- Consequences: Phase 3 can build and verify the Taipei demo path without spending time on all-city parameter tuning. Kaohsiung sensitivity, H3/DBSCAN alternatives, and full-city reproducibility remain deferred scope for a later approved expansion.
- Reversible: Yes; reopening all-city clustering requires a new decision and active plan.
- Approval: User approved the Taipei Demo scope and Phase 3 transition on 2026-09-19.

### D-009 — Taipei serving baseline is area attraction plus personal mobility

- Status: Accepted
- Date: 2026-09-21
- Context: Phase 3 must choose its deterministic serving model using Train-only feature fitting, Validation selection, and a locked Test evaluation. The candidate similar-rider component B is only usable for riders with enough history and at least five effective neighbors.
- Options: Keep Origin-Period Popularity as the serving model; serve A+C (area attraction plus personal mobility); or enable A+B+C for all supported riders.
- Decision: Serve area_a_plus_c with weights A=0.30, C=0.70 in the Taipei Demo. Disable B by default. Cold riders continue with the explicit non-personalized fallback instead of inventing a personal score.
- Evidence: data/features/phase3_taipei/evaluation/personalized_evaluation_v2.json, report hash 2b8984f3b7ee34e749370f7abba0fa13d79d1c2d618eb03afb226cbcc87d2b76. Validation selected A+C by highest HitRate@5 then MRR with the simpler-model tie-break; Test was run after that lock. On Test, A+C achieved HitRate@5 0.4828 and MRR@5 0.3866, versus Origin-Period Popularity 0.3863 and 0.2450. A+B and A+B+C did not beat A+C on Validation, so B is not an evidence-supported serving addition.
- Consequences: Phase 4 API and Phase 6 UI expose A/C evidence and B as unavailable, rather than claiming social-similarity personalization. This decision is Taipei Demo only; it does not support a national or production-quality claim.
- Reversible: Yes. Re-enable B only through a new Train/Validation/Test evaluation version and recorded decision.
- Approval: Agent review authorized by the user on 2026-09-20; the Phase 3 independent Luna high review found and corrected a DistanceFit defect before this v2 evaluation.

### D-010 — Provider integrations are opt-in and never persist Places content

- Status: Accepted
- Date: 2026-09-21
- Context: Phase 5 needs a real-key mode without making provider access, billing, or data-retention a prerequisite for the Taipei Demo.
- Options: Require Google keys; cache full Places responses; or use opt-in live calls with a legal keyless fallback.
- Decision: Google Places and Routes are called only when a server-side key exists. Places uses Nearby Search POST, a minimal explicit FieldMask, 2.5-second timeout, at most one retry with jitter for timeout/429/5xx, deduplication, one radius expansion, and one next-area search. No Places response is persisted; only the response for the current request is used. Any insufficient or failed response uses repository-owned synthetic restaurant data. Routes only requests distance and duration; failure uses Haversine × 1.30.
- Evidence: Google official Nearby Search and policy documentation consulted 2026-09-21; 44 Python tests pass, including mocked keyless, timeout, 429, 5xx, malformed, deduplication, and minimal-FieldMask cases.
- Consequences: The Demo remains usable with no Google account, while a configured key has bounded, policy-conscious behavior. UI must visibly identify fallback data and must not imply Google data is stored.
- Reversible: Yes, only with a new policy review and decision.
- Approval: Agent authority delegated by the user.

### D-011 — Extend the Taipei Demo with inspectable live calculation and Google map rendering

- Status: Accepted
- Date: 2026-09-21
- Context: The completed demo uses real offline artifacts but currently renders a CSS test map, narrows restaurant candidates too early, and does not expose Routes polylines. The user approved a change that visibly connects deterministic area ranking, live restaurant retrieval, route estimates, and map rendering.
- Options: Only populate existing Google environment variables; replace the static map while retaining simplified ranking; or align serving with the locked A+C model and make the full bounded candidate-to-route process inspectable.
- Decision: Create Phase 9. Keep offline fitting unchanged and Train-only. At request time, rank bounded Taipei area candidates with the accepted A+C model, retrieve ephemeral Places candidates, calculate bounded route matrix estimates, rank restaurants with documented contextual and POI-quality components, and retrieve a full route polyline only for a selected restaurant. Render the returned trace on Google Maps when a browser-restricted key exists; otherwise retain an explicit static fallback. Do not persist Places content or show raw trip paths.
- Evidence: User approval in the Codex task on 2026-09-21; existing artifacts contain a 102-area Taipei model and locked A+C evaluation; Google Routes documentation confirms `computeRouteMatrix` does not return polylines and `computeRoutes` returns an encoded polyline when requested with an explicit FieldMask.
- Consequences: The API and database loader need versioned response and feature-field extensions, and the frontend needs a provider abstraction for Google Maps versus the static fallback. Live acceptance requires user-managed Google billing, API enablement, and restricted keys; implementation and keyless tests do not.
- Reversible: Yes. The existing static fallback remains available, and the original API fields remain backward-compatible during migration.
- Approval: User approved on 2026-09-21.

### D-012 — Add a serving-time proximity guardrail and area-diverse restaurant shortlist

- Status: Accepted
- Date: 2026-09-22
- Context: The locked historical area model can select a high-scoring distant area for a Taipei Main Station origin, especially for cold users where personal mobility is unavailable. The live Places shortlist can then let that first area's restaurants occupy the whole Top 5.
- Options: Refit or retune the offline A+C model; blacklist individual districts; add a serving-time distance guardrail and diversify live restaurant candidates; or leave the behavior unchanged and explain the long trip in the UI.
- Decision: Keep the Train-only offline model and its locked A=0.30/C=0.70 evaluation unchanged. At serving time, use an 8 km road-distance budget for cold users and a bounded `1.5 × median_distance_km` budget for supported personas, clamped to 6–10 km. Rank eligible areas with the existing model score plus a 20% proximity fit. Select live route candidates round-robin across ranked areas with a target cap of two restaurants per area; if the provider supplies only one area, fill enough candidates to preserve the Top 5 contract. Expose the budget and proximity weight in the safe calculation trace.
- Evidence: The local Taipei artifact ranks the Wenshan-side `taipei_area_0040` at about 10.66 km for the Taipei Main Station dinner example, while nearby areas have slightly lower attraction scores. The user approved this serving behavior change in the Codex task on 2026-09-22.
- Consequences: Default Demo results should be nearer and less concentrated in one district. The behavior is a serving policy, not evidence that users prefer nearby restaurants; offline HitRate/MRR remains comparable to D-009 only when the guardrail is reported separately. A future exploration mode may intentionally relax the budget and must be labelled as such.
- Reversible: Yes. Remove the serving parameters and shortlist policy while retaining the offline artifacts; update this decision and the active plan with replacement evidence.
- Approval: User approved on 2026-09-22.

### D-013 — Keep consumer-facing copy focused on the next decision

- Status: Accepted
- Date: 2026-09-23
- Context: The Phase 9 frontend exposed model stages, weights, scores, fallback terminology, and test controls in the normal restaurant flow. The user requested a complete plain-language copy pass that reads like a real product and avoids showing every calculation.
- Decision: Show location, restaurant choices, travel estimates, and short grounded reasons in the normal UI. Keep scoring and factual calculation traces in API responses and automated tests for review, rather than exposing them in the consumer flow. Clearly label synthetic restaurants, the static map illustration, historical fare estimates, and the non-booking ride preview. Keep the service-outage test location available only through the explicit `showTestLocations` query parameter.
- Evidence: User request on 2026-09-23; `npm --prefix frontend run test:run`, `npm --prefix frontend run build`, `npm --prefix frontend run e2e -- --workers=1 --reporter=line` against a fresh Vite server, and `.\.venv\Scripts\python.exe -m pytest backend/tests/test_recommendation_api.py -q` passed after the copy change.
- Consequences: Reviewers inspect score and stage details through the API rather than a consumer-facing panel. The map, selection flow, ranking, provider fallbacks, and feedback contracts remain in place.
- Reversible: Yes. A separately designed reviewer view can present the existing API trace without reintroducing technical details to the consumer flow.
- Approval: User explicitly requested the consumer-facing copy change on 2026-09-23.

### D-014 — Label sample restaurant reviews and ratings as simulated

- Status: Accepted
- Date: 2026-09-23
- Context: The user requested that opening a recommended restaurant show user-review-like content with text and a one-to-five-star rating. The existing product can show live Places restaurants, so invented reviews could otherwise be mistaken for real customer feedback.
- Decision: Add a clearly labelled simulated review section in restaurant detail. Each illustrative text review has a one-to-five-star score. Let the viewer select a one-to-five-star demo rating, but keep it in page state only and explicitly say it is not submitted or saved. Do not use restaurant photos or persist or report simulated reviews as real feedback.
- Consequences: The detail view demonstrates the review and rating interaction without making a claim about restaurant reputation or recording a user opinion. Live Places ratings, when present, remain separately identified as the restaurant's public rating.
- Reversible: Yes; remove the detail section without changing recommendation or feedback APIs.
- Approval: User requested this behavior on 2026-09-23.

### D-015 — Keep the source repository private and exclude local data

- Status: Accepted
- Date: 2026-09-23
- Context: D-002 limited Git to local metadata. The user later asked to put this project in a new GitHub repository and chose private visibility. The local workspace contains raw trips, derived artifacts, environment secrets, and dependency/build output that must not accompany the source code.
- Decision: Create `hyslchs/Hotai-Hackathon` as a private GitHub repository and push the reviewed source on `main`. Treat `data/` as excluded by default; allow only its data dictionary, README, placeholders, and the explicitly named hand-authored fallback restaurant fixture. Keep raw trips, processed rows, fitted artifacts, `.env`, keys, local databases, dependencies, and build output out of Git.
- Evidence: The initial source commit `8d8affd` contained 118 files; the largest tracked file was 100,316 bytes. `scripts/check_tracking.ps1` passed for all 118 files, and the raw CSV Git blob was absent from `main` history. GitHub showed the repository as Private with the pushed `main` branch.
- Consequences: Authorized collaborators can review the code and instructions. A fresh clone requires separately authorized input data and local artifact generation for the complete backend demo. Repository visibility or deployment requires a separate user decision.
- Approval: User requested the new repository and explicitly chose private visibility on 2026-09-23.

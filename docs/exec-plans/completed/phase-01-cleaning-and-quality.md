# Phase 1 cleaning and quality

## Purpose and observable outcome

把 supplied trip CSV 以可重跑、低記憶體、不可覆寫 raw 的方式轉成：

- data/processed/trips_clean.parquet
- data/processed/trips_quarantine.parquet
- data/reports/quality_report.json
- data/reports/quality_report.md
- data/reports/run_manifest.json

品質報告必須讓新手看得懂：總列數如何分到 clean/quarantine、每個 hard-invalid 與 soft-outlier 規則各自影響多少列、soft-outlier 聯集多少列、Train/Validation/Test 如何切分，以及哪些項目仍需要人工決策。

本階段只做清理與品質基礎，不做 clustering、features、similar-rider、ranking、evaluation、database loading 或 API recommendation。

目前狀態：Completed，實作與自動驗收完成於 2026-09-18；使用者於 2026-09-18 核准 Phase 1，並授權以 soft-outlier 敏感度比較開始 Phase 2。

## Progress

- [x] 2026-09-18，確認 Phase 0 已完成並封存；roadmap 允許進入 Phase 1。
- [x] 2026-09-18，重新確認 supplied CSV 位於 data/yoxi_rawdata.csv，header 為 14 欄，logical rows 為 964991，Phase 0 parser rejects 為 0。
- [x] 2026-09-18，建立 chunked/streaming cleaner、hard-invalid quarantine 與 soft-outlier counters。
- [x] 2026-09-18，建立衍生欄位、時間切割與 Parquet writers。
- [x] 2026-09-18，建立 quality JSON/Markdown、manifest、input/artifact hashes 與 reproducibility test。
- [x] 2026-09-18，將 make preprocess 改成實際入口，更新 bootstrap 依賴與 README。
- [x] 2026-09-18，完成完整 Phase 1 acceptance：exact split counts、raw reconciliation、May 1 after-midnight rows 與 rerun stability 均符合。
- [x] 2026-09-18，使用者完成人工審查：soft-outlier 保留在資料與報告、第一版模型暫不使用，允許以納入／排除比較開始 Phase 2。

## Surprises and discoveries

- Phase 0 audit 已確認 supplied CSV 的 exact logical row count 是 964991，與 PROJECT_SPEC.md 一致；CSV 物理行數不可直接代替 logical CSV rows。
- supplied file 路徑不在 data/raw/，Phase 1 必須沿用 Phase 0 的候選路徑解析，不得複製或搬移 raw file。
- Phase 0 parser 已經提供 Asia/Taipei aware datetime、fare [100,200] 的 101 至 200 interpretation、nullable POI 與 exact source columns；Phase 1 應重用它，不要建立第二套互相矛盾的 parser。
- 尚未確認 hard-invalid、soft-outlier、city bucket 與 split 的實際分布；這些必須由本階段報告產出，不能先寫成結論。
- 實際清理結果為 0 hard-invalid、1,642 列至少觸發一個 soft-outlier rule；model-eligible 為 Train 451,618、Validation 169,609、Test 342,122。這是資料品質觀察，不是模型品質結論。
- 實際 input path 是 `data/yoxi_rawdata.csv`；`make data-audit` 與兩次 pipeline run 都觀察到 964,991 logical rows，input SHA-256 為 `c5d633e5ebb9dd7f7010bf40064a2f843748ea46589fa6c72ab6f70f57c28faa`。
- Phase 1 初始 `npm install` 曾回報 5 個 dependency vulnerabilities（3 moderate、1 high、1 critical）。使用者核准後已將 `vite` 升至 6.4.3、`vitest` 升至 5.0.1；目前 `npm audit` 與 `npm audit --omit=dev` 都是 0 vulnerabilities，測試與 build 仍通過。

## Decision log

- Decision: Phase 1 使用 Python stdlib csv 逐列解析、固定大小 chunk 累積，再以 PyArrow ParquetWriter 逐批寫檔。Rationale: 能保留明確的 row-level quarantine 原因，又不需把約 965k rows 全部載入記憶體。Date: 2026-09-18. Human approval not required unless measurements show this cannot finish reliably.
- Decision: 使用 PyArrow 作為 Parquet writer，版本固定在 pipeline/requirements.txt；不引入 Pandas 作為必要 runtime。Rationale: Phase 1 只需要 typed columnar output，減少依賴與隱式型別轉換。Date: 2026-09-18.
- Decision pending evidence: soft-outlier thresholds remain the PROJECT_SPEC.md §10.2 initial rules until rule-level counts、region/date distribution and model-eligibility impact are reviewed. Phase 1 must report evidence; it must not silently change thresholds.
- Decision pending evidence: city report uses documented deterministic coordinate buckets labelled Taipei, Taichung, Kaohsiung, Other/Unknown. These are audit buckets, not an official geocoder or clustering result; change only if the report shows the buckets are misleading.
- Decision: Train/Validation/Test split is assigned from normalized started_at and is recorded even for soft outliers; model_eligible controls later training eligibility. Rationale: the required 452333/169934/342724 counts are before model exclusions. Date: 2026-09-18.

## Outcomes and retrospective

Phase 1 automated acceptance completed on 2026-09-18 with exit code 0 for all required commands:

- `mingw32-make PYTHON=.venv/Scripts/python.exe bootstrap`: dependencies already satisfied; `.env` preserved.
- `mingw32-make PYTHON=.venv/Scripts/python.exe data-audit`: exact 14-field header, 964991 logical rows, 0 wrong-width rows, 0 Phase 0 contract rejects.
- `mingw32-make PYTHON=.venv/Scripts/python.exe preprocess`: input 964991, clean 964991, quarantine 0, reconciled `True`; split counts Train 452333, Validation 169934, Test 342724; soft-outlier union 1642.
- `mingw32-make PYTHON=.venv/Scripts/python.exe test`: Python 14 passed, frontend 1 passed, Vite production build passed; one existing Starlette/AnyIO deprecation warning.
- `mingw32-make safety-check`: PASS, 0 tracked files outside the safety boundary.
- Isolated rerun to `data/processed/.phase1-repro` and `data/reports/.phase1-repro`: report JSON, manifest, Parquet physical SHA-256 and Parquet content SHA-256 all equal to the primary run.

Quality evidence:

- `boundary_counts.may1_after_midnight_test_rows` is exactly 40.
- Hard-invalid rule counts are empty and quarantine has a stable schema with 0 data rows.
- Soft-outlier counts are: `distance_zero=358`, `speed_low=948`, `speed_high=148`, `travel_time_long=328`, `distance_long=30`, `elapsed_time_mismatch=272`; union is 1642.
- Clean Parquet schema is timezone-aware Asia/Taipei for the datetime fields and includes derived fields; quarantine retains source fields plus row number and rule names.
- Primary artifacts: `data/processed/trips_clean.parquet` SHA-256 `49594cb830f57ed80f2820d8ae39b8e8f1ef394acba0729ff9935c614b0c4870`, content SHA-256 `49bc46638a6fc1a78ff6cff386651e14689ffea0220e76374f4b5ed29064944e`; `trips_quarantine.parquet` SHA-256 `15ba99dd03ea829cdfbb38d655c6604d484b4c8f919a7b6d80192540cd06a44a`, content SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Reports: `quality_report.json` SHA-256 `003fbddf5354767d4eda59be24fe32d3b275f73470e4713f05183e0db84004c7`; `quality_report.md` SHA-256 `2eec64377e90a835274a29b9b44bee8b597616cfdc1ad06d00394a846112b455`.

Retrospective and limits: the pipeline reads the raw CSV and writes only ignored generated outputs; it does not modify raw data. The 0 quarantine result means the supplied file currently contradicts none of the hard-invalid rules, not that future inputs are guaranteed clean. The soft thresholds and coordinate buckets are initial audit rules from the specification and remain proposed for review. No clustering, model fitting, ranking, database loading, or recommendation API work was started.

## Context and orientation

Input contract:

- Source columns are the exact SOURCE_FIELDS in pipeline/cleaning/contract.py.
- All timestamps become Asia/Taipei aware datetimes.
- Fare [100,200] means lower-exclusive 101 and upper-inclusive 200, with midpoint 150.5.
- Raw input is never overwritten.
- RiderId is sensitive. It may remain in local ignored Parquet needed for later offline analysis, but it must not appear in reports, ordinary logs, frontend output, screenshots or committed fixtures.

Required split boundaries from PROJECT_SPEC.md §10.1:

- Train: started_at < 2026-03-16 00:00:00, target 452333 rows.
- Validation: started_at >= 2026-03-16 00:00:00 and < 2026-04-01 00:00:00, target 169934 rows.
- Test: started_at >= 2026-04-01 00:00:00 through the source end, target 342724 rows.
- The 40 trips after midnight on May 1 remain in Test.

Hard-invalid rows are quarantined and excluded from clean output:

- required field cannot parse
- duplicate trip id
- ended_at earlier than started_at
- ordered_at later than started_at
- latitude outside 20 to 27 or longitude outside 118 to 123
- travel_time_min <= 0
- travel_distance_m < 0
- fare range cannot parse

Soft-outlier rows remain in clean output with model_eligible false and exclusion_reasons:

- travel_distance_m == 0
- speed below 1 km/h or above 120 km/h
- travel_time_min > 180
- travel_distance_m > 200,000
- absolute elapsed-time versus TravelTime difference > 2 minutes

Derived fields:

- weekday_class: weekday or weekend
- period: morning 05:00–10:59, lunch 11:00–13:59, afternoon 14:00–16:59, dinner 17:00–20:59, night 21:00–04:59
- distance_km
- elapsed_time_min
- speed_kph
- fare_midpoint
- model_eligible
- exclusion_reasons
- split

## Scope

In scope:

- chunked source ingestion and path selection
- row validation and hard-invalid quarantine
- soft-outlier rule counters and aggregate distributions
- derived fields and exact time split
- clean/quarantine Parquet output
- quality JSON and readable Markdown report
- deterministic manifest and rerun stability
- pipeline requirements, Makefile preprocess target, tests and README instructions

Out of scope:

- geographic clustering or HDBSCAN
- area features, A/B/C/D scores, similar riders or ranking
- model evaluation or any Test-fit artifact
- database migrations/loading
- backend recommendation endpoints
- frontend feature work
- external Places, Routes or LLM calls
- changing the supplied raw data or committing generated Parquet

## Plan of work

First implement the pipeline entry point that selects RAW_DATA_PATH if it exists, then the expected data/raw path, then the observed supplied data/yoxi_rawdata.csv path. Open with utf-8-sig and csv.reader so logical rows, not physical newlines, are counted.

For every row, preserve a safe row number for diagnostics, run the existing contract parser, apply hard-invalid rules, and maintain a duplicate trip-id set across chunks. Hard-invalid rows go to quarantine with source fields and non-sensitive rule names. Do not print row values or rider identifiers.

For valid rows, compute timezone-aware derived fields and assign the time split. Apply each soft-outlier rule independently, store all triggered rule names in deterministic order, and set model_eligible false if any soft rule triggers. Write clean rows and quarantine rows through fixed Arrow schemas and ParquetWriter in chunks.

At the end, write aggregate-only reports. Every rule needs a total count; soft rules also need union count, audit region distribution and started-date distribution. The manifest includes input size/hash, configuration, Python/package versions, raw/clean/quarantine counts, split counts, output names and output hashes. It must not include raw row samples or RiderId.

Finally run the pipeline twice into separate temporary output directories and compare canonical manifest fields, report JSON, counts and artifact hashes. If Parquet physical hashes differ while canonical row hashes match, record the cause and use canonical content hashes for reproducibility claims.

## Milestones

### Milestone 1 — Streaming ingestion and rule engine

Observable state: a clean function can process the observed CSV in bounded chunks, reuse the Phase 0 parser, classify every logical row, and produce per-rule counters without printing sensitive values.

Acceptance: a unit fixture covers each hard and soft rule, duplicate IDs across chunk boundaries, exact fare/time behavior, and deterministic reason ordering.

### Milestone 2 — Parquet outputs and split contract

Observable state: clean and quarantine Parquet files exist locally, raw plus outputs reconcile exactly, and clean split counts are reported for Train, Validation and Test.

Acceptance: counts match 452333, 169934 and 342724 before model exclusions; 40 May 1 after-midnight rows are in Test.

### Milestone 3 — Quality report and reproducibility

Observable state: JSON and Markdown reports show rule counts, soft union, audit region/date distributions, exclusions, split counts, artifact hashes and configuration without raw identifiers.

Acceptance: same input/config rerun produces equivalent canonical report and artifact content hashes; no raw input is changed.

### Milestone 4 — Stable command and handoff

Observable state: make preprocess runs the pipeline; bootstrap installs pipeline dependencies; tests cover the phase; README and this plan describe recovery and exact output locations.

Acceptance: full Phase 1 commands pass, plan status becomes Completed after human approval, roadmap Phase 1 becomes Completed, and the next Phase 2 plan is created only after the approval gate.

## Concrete commands and expected observations

From F:/Project/Hotai-Hackathon:

- mingw32-make PYTHON=.venv/Scripts/python.exe bootstrap
  Expected: pipeline dependencies install from pinned pipeline/requirements.txt; existing .env is not overwritten.
- mingw32-make PYTHON=.venv/Scripts/python.exe preprocess
  Expected: exit 0; clean and quarantine Parquet plus reports and manifest are written under ignored data/processed and data/reports.
- mingw32-make PYTHON=.venv/Scripts/python.exe test
  Expected: Phase 0 tests plus Phase 1 tests pass; frontend test/build still pass.
- mingw32-make PYTHON=.venv/Scripts/python.exe data-audit
  Expected: source contract remains exact and raw count remains 964991; no cleaning is performed by this command.
- Get-Content data/reports/quality_report.json
  Expected: aggregate counts only; no raw identifiers or row samples.
- Get-Content data/reports/quality_report.md
  Expected: readable summary including reconciliation, hard rules, soft rules, regions, dates, split counts and limitations.
- mingw32-make PYTHON=.venv/Scripts/python.exe preprocess
  Expected on rerun: same canonical counts, report values and artifact content hashes.
- docker compose commands are not needed for Phase 1 pipeline execution; do not use Phase 2 clustering targets.

## Validation and acceptance

Phase 1 is accepted only when all are recorded here:

- raw logical rows equal clean rows plus quarantine rows, exactly 964991
- clean split counts equal Train 452333, Validation 169934 and Test 342724 before model exclusions
- May 1 after-midnight count is 40 and split is Test
- every hard-invalid rule has an independent count and quarantine output
- every soft-outlier rule has an independent count, union count, audit region distribution and audit date distribution
- derived period/weekday/timezone/fare fields pass boundary tests
- clean and quarantine Parquet schemas are stable and readable
- rerun with same input/config yields equivalent canonical reports and artifact content hashes
- raw CSV is unchanged and no generated sensitive artifact is tracked
- Phase 1 tests, preprocess and full test target pass
- README, ROADMAP, DECISIONS and this plan match observed reality

Do not claim a model-quality conclusion from Phase 1. If observed data contradicts the source contract or expected split counts, stop at Needs review with samples replaced by aggregate diagnostics and do not begin Phase 2.

## Idempotence and recovery

Never delete raw data or use destructive Git commands. If a run is interrupted, remove only the explicitly named temporary output directory after checking it is inside data/processed or data/reports, then rerun. Prefer writing to a run-specific temporary directory and atomically moving final artifacts after validation.

If a Parquet writer fails, keep the manifest/log information, inspect schema and disk space, and rerun with the same config. If a row cannot parse, quarantine its source fields locally with rule names; do not guess values. If a report would include RiderId or raw samples, fail the report generation and remove only that generated report file after confirming its exact path.

## Interfaces and artifacts

- pipeline/cleaning/contract.py remains the single source parser.
- pipeline/cleaning/preprocess.py owns chunk iteration, rule classification, derived fields and Parquet writing.
- pipeline/tests/test_preprocess.py covers rules and split boundaries.
- scripts/preprocess.py is the stable command entry point.
- pipeline/requirements.txt pins PyArrow.
- data/processed/trips_clean.parquet and trips_quarantine.parquet are ignored local artifacts.
- data/reports/quality_report.json, quality_report.md and run_manifest.json are ignored local artifacts.
- Makefile preprocess target invokes scripts/preprocess.py.
- No report prints raw rows, rider IDs, raw POI text or provider responses.

## Handoff

Fresh-session first action: read AGENTS.md, this plan, docs/PROJECT_SPEC.md sections 3, 6, 10.1, 10.2, 18.1 and 19, docs/ARCHITECTURE.md, docs/DECISIONS.md, then run git status --short --branch --ignored.

First implementation action: inspect the existing Phase 0 parser and supplied CSV through aggregate diagnostics, then add the pinned PyArrow dependency and implement the smallest chunked pipeline.

At completion: exact evidence is recorded above, the user approved the Phase 1 gate on 2026-09-18, and this plan is ready to move to completed/. Phase 2 continues under its own active ExecPlan with an included-versus-excluded soft-outlier comparison.

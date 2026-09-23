# Architecture map

本文件只提供系統導覽與依賴邊界。精確公式、欄位、錯誤格式與驗收門檻以 `docs/PROJECT_SPEC.md` 為準；已核准的偏離以 `docs/DECISIONS.md` 為準。

## End-to-end flow

原始匿名行程先經 offline pipeline 解析、隔離異常、時間切割、地理群聚與特徵計算，再產生帶有 `model_version` 的 serving artifacts。Loader 將 artifacts 寫入 PostgreSQL。推薦 API 依 demo rider alias、目前位置與時間，先排序目的區域，再由 Places 或合法 fallback 取得餐廳，加入當下情境與 POI 品質後產生 Top 5。Explanation service 只能把結構化證據轉成短句。React 前端呈現地圖、推薦詳情、技術依據與模擬叫車，互動事件回寫後端。

## Subsystems and ownership

| Subsystem | Target paths | Responsibility | Read in spec |
| --- | --- | --- | --- |
| Offline ingest and quality | `pipeline/cleaning/`, `data/processed/`, `data/reports/` | Schema parsing, quarantine, split, reproducibility | §§3, 10.1–10.2, 18.1 |
| Geographic areas | `pipeline/clustering/` | Train-only area model, experiment report, assignment | §10.3 |
| Features and evaluation | `pipeline/features/`, `pipeline/similarity/`, `pipeline/evaluation/` | A/B/C features, baselines, calibration, held-out evaluation | §§11–12, 18.2 |
| Artifact loading and database | `pipeline/loading/`, `backend/app/db/`, `backend/migrations/` | Versioned serving schema and atomic loading | §13 |
| Recommendation backend | `backend/app/services/recommendation/`, `backend/app/api/v1/` | Candidate filtering, ranking, stable response contracts | §§11, 14, 17–18 |
| External adapters | `backend/app/services/places/`, `routes/`, `explanation/` | Timeouts, retries, FieldMask, legal fallback, deterministic explanation | §§11.6–11.8, 15, 17 |
| Ride and feedback | `backend/app/services/ride/`, API and repositories | Historical estimate, demo confirmation, idempotent events | §§13–15 |
| Frontend | `frontend/src/` | Mobile-first map and bottom-sheet state machine | §16, §§18.4–18.5 |
| Runtime and checks | `docker-compose.yml`, `Makefile`, `scripts/` | Repeatable setup, tests, health and demo readiness | §§7–9, 19 |

## Dependency direction

The pipeline may read `data/raw/` but application code must not. The backend consumes versioned artifacts or database rows; it must not fit models at request time. API routes validate and translate transport data, services own business rules, repositories own persistence, and external providers sit behind adapters. Frontend code depends only on the documented HTTP contract and never on server secrets or real rider identifiers.

Keep these boundaries mechanically testable where practical:

- Parsing and validation occur at file, API, database, and external-service boundaries.
- Ranking functions receive typed, normalized inputs and do not call network services.
- External adapters return explicit success, unavailable, timeout, and malformed-response outcomes.
- Fallback selection is visible in the response and logs.
- Pipeline artifacts carry split metadata, configuration, seed, input fingerprint, and `model_version`.

## Invariants

- No random train/validation/test split and no fitting on Validation or Test.
- No real `RiderId` in frontend responses, ordinary logs, screenshots, or committed fixtures.
- No LLM influence on numeric ranking.
- Missing components are unavailable, not zero; weights are renormalized and the reason is observable.
- Stable tie-breaking makes the same version and input reproducible.
- Places, Routes, and LLM failures degrade independently and do not prevent the core demo when fallback data is valid.
- Readiness reflects local dependencies and required artifacts, not optional external-provider uptime.

## Architecture decisions that must be recorded

Record evidence and consequences in `docs/DECISIONS.md` when choosing clustering parameters or fallback, changing cleaning thresholds, accepting model weights, enabling or removing similar-rider component B, selecting persistence formats, changing API contracts, using brand assets, or changing third-party data retention behavior.


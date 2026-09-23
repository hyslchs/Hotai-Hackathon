# Phase 0 foundation and data contract: Completed

## Purpose and observable outcome

建立可重現、可安全檢查的 yoxi AI Demo 基礎。新貢獻者應能安裝 Python 3.12 與 frontend 依賴、執行 foundational tests、啟動 FastAPI 與 PostgreSQL/React 的 Compose stack，並在不提交原始 CSV、secret 或 RiderId 對照表的前提下驗證 14 欄資料契約。

本階段不做資料清理、quarantine、時間切割、HDBSCAN、推薦排名、Places/Routes/LLM、正式 UI 或 Phase 1 以後的工作。

目前狀態：Completed，時間 2026-09-18T05:20:00Z。Docker 內外連線設定已永久分離；Compose 重新建置後 PostgreSQL healthy、frontend 200、/health/live 200、/health/ready 200。使用者已確認 Phase 0 可進入下一階段。

## Progress

- [x] 2026-09-18T03:15:00Z，檢查初始樹、git status、runtime 與附件；初始目錄只有規劃文件，沒有 Git metadata 或 application code。
- [x] 2026-09-18T03:28:27Z，filesystem refresh 後重新檢查 supplied CSV 與 data dictionary，僅做 aggregate/contract audit，沒有搬移、複製或輸出 raw rows。
- [x] 2026-09-18T03:28:27Z，依目標邊界建立 backend、frontend、pipeline、data、scripts 與安全設定；沒有既有 application code 可重用或需要保留。
- [x] 2026-09-18T03:28:27Z，建立 exact-pinned backend requirements、frontend package-lock、Python 3.12 venv、Docker Compose 及環境變數界線。
- [x] 2026-09-18T03:28:27Z，建立 typed 14-field parser、fare/time boundary、nullable POI handling 與 deterministic synthetic 1,000-row fixture generator。
- [x] 2026-09-18T03:28:27Z，建立 FastAPI live/ready、React/Vite placeholder、Compose syntax check 與安全檢查。
- [x] 2026-09-18T03:28:27Z，建立 Make targets 並通過 bootstrap、data-audit、test、safety-check；bootstrap 第二次執行保留既有 .env。
- [x] 2026-09-18T03:28:27Z，完成 Phase 0 evidence，更新 roadmap 與 decisions，停在 Needs review；未開始 Phase 1。

## Surprises and discoveries

- 2026-09-18 初次 git status 回報不是 Git repository，Test-Path .git 為 False。這不是既有 checkout，而是只有文件的工作目錄；沒有未提交 application change 可覆蓋。
- 後續 filesystem refresh 出現 data/yoxi_rawdata.csv 與 data/data_dictionary.md。CSV 的 header 正好是規格定義的 14 欄，安全 audit 觀察到 964991 個 logical rows、0 個錯誤欄數 row、0 個 Phase 0 parser rejects。
- supplied CSV 位於 data/ 根目錄，而非目標 layout 的 data/raw/。沒有搬移使用者資料；.gitignore 額外忽略 data-level CSV/Parquet，audit 會依 RAW_DATA_PATH、標準 data/raw 路徑、再依 supplied local candidate 選檔。
- node 版本為 v24.12.0，npm 為 11.6.2，Docker Compose 為 v5.5.0。預設 python/py launcher 失效，但實際 Python 3.12.2 位於 C:/Users/hyslc/AppData/Local/Programs/Python/Python312/python.exe，已用它建立 .venv。
- docker compose config --quiet 在第一次產生的 YAML 發現變數插值前多了一個反斜線；修正後 config check 通過。沒有因這個錯誤啟動或刪除 container。
- Docker 啟動後，將 DATABASE_URL 暫時設為 postgresql+psycopg://postgres:postgres@postgres:5432/yoxi 後，/health/live 與 /health/ready 都回傳 200。根因是 .env 的 localhost 只適用於 host 上直接執行 backend；Docker container 內的 localhost 指向 backend 自己，PostgreSQL 應使用 Compose service name postgres。
- 2026-09-18: 永久修正新增 DATABASE_URL_DOCKER，Compose backend 明確使用 postgres service name；重新 docker compose up -d --build 後，postgres 為 healthy，frontend、live、ready 均回傳 200。
- npm install 產生 frontend/package-lock.json。npm audit --omit=dev 報告 0 個 production vulnerabilities；完整 audit 有 5 個 transitive development-tool findings，沒有在本階段強制升級。
- Docker Compose 曾因 Docker Desktop 未啟動而暫時無法執行；Docker Desktop 啟動後已完成完整服務驗證。

## Decision log

- Decision: 適配空的既有目錄，不替換既有使用者程式碼。Rationale: repository guide 要求先保存既有變更；本次實際觀察沒有 application code。Date: 2026-09-18。
- Decision: synthetic fixture 的 RiderId 必須是新生成、不可反查的測試值，不得從 raw dataset 保留 mapping。Rationale: RiderId 是 pseudonymous identifier。Date: 2026-09-18。
- Decision: 使用 exact pins：backend requirements 固定 FastAPI 0.115.6、Pydantic 2.10.5、psycopg 3.2.3、uvicorn 0.34.0、httpx 0.28.1、pytest 8.3.4；frontend 固定 React 18.3.1、Vite 6.0.7、TypeScript 5.7.3、Vitest 2.1.8，並提交 package-lock。Rationale: 沒有既有 package choice，reproducible bootstrap 是驗收條件。Evidence: pinned install and tests passed. Human review not required to use the pins in Phase 0, but later upgrades need evidence.
- Decision: 初始化 local Git metadata，但不 stage、commit、push、建立 remote 或改 remote configuration。Rationale: tracked-file safety checker 需要可執行的 Git repository。Evidence: git init succeeded; safety check and ignore checks pass. Review requested.
- Decision: 保留 supplied CSV 原路徑，額外忽略 data-level CSV/Parquet，不複製 raw file 到 data/raw。Rationale: 不擅自搬移或複製使用者資料；Phase 1 再決定 canonical ingestion path。Evidence: data-audit exact count/header and git check-ignore pass. Review requested.

## Outcomes and retrospective

已完成的 observable outcomes：

- backend/app/main.py 提供 GET /health/live 與 GET /health/ready。沒有 DB 時 live 為 200，ready 為 503 並回傳 DB_UNAVAILABLE、retryable true 的安全 error shape，不泄漏 psycopg exception 或 connection string。
- pipeline/cleaning/contract.py 接受 exact 14 fields，時間正規化為 Asia/Taipei aware datetime，fare [100,200] 解析為 101 至 200、midpoint 150.5，空白 POI 變成 None，無效值明確拒絕。
- pipeline/tests/fixtures/synthetic.py 每次產生 1,000 筆 synthetic rows；不含 real rider lookup table。10 個 Python tests 全部通過，包含 parser、fare、datetime、config、live/ready。
- frontend 有 Phase 0 placeholder、沒有 server-only key；1 個 Vitest 測試通過，Vite production build 通過。
- make bootstrap 已執行兩次；第二次顯示 kept existing .env，沒有覆蓋設定。frontend/package-lock.json 已產生。
- make data-audit 顯示 source_file=data/yoxi_rawdata.csv、observed_rows=964991、row_count_matches_spec=True、rows_with_wrong_column_count=0、rows_rejected_by_phase0_contract=0；audit 沒有清理或改寫 CSV。
- tracking checker 通過。git check-ignore 確認 .env、data/yoxi_rawdata.csv、.venv、frontend/node_modules、frontend/dist 都被忽略。沒有檔案被 stage 或 commit。
- docker-compose.yml 經 docker compose config --quiet 驗證通過。直接啟動 FastAPI 得到 live_status=200、ready_status=503；永久分離連線設定後 Compose 得到 live_status=200、ready_status=200。

後續工作：

- Phase 0 沒有產出 clean/quarantine Parquet、split、clusters、models 或 recommendations；這些已明確交給 Phase 1 及後續階段。
- 完整 npm audit 的 5 個開發依賴 transitive findings 未處理；production-only audit 為 0。後續若要升級套件，需另有相容性證據。
- 沒有建立 remote、PR、deployment、paid service 或外部 API configuration。

## Context and orientation

目標 runtime boundaries：

- backend/：Python 3.12 FastAPI，必要 readiness dependency 是 PostgreSQL 16。
- frontend/：React、TypeScript、Vite；瀏覽器只接收 VITE_BACKEND_URL，不保存 Places、Routes、LLM secrets。
- pipeline/cleaning/：typed source row boundary；Phase 1 才加入清理與輸出。
- data/raw/、data/processed/、data/reports/：raw/generated data 都受 ignore rule 保護。
- scripts/：audit、bootstrap、tracking check、尚未開放 phase 的明確 non-success placeholder。
- Makefile、docker-compose.yml、README.md：穩定入口與本機啟停說明。

規格真相來源仍是 docs/PROJECT_SPEC.md、docs/ARCHITECTURE.md 與 docs/DECISIONS.md；本計畫只記 Phase 0 狀態。Ranking、fit、scaler、cluster 與模型尚未建立，所以沒有任何 future-phase claim 可以由本階段支持。

## Scope

In scope：

- repository directories and Git safety boundary
- Python 3.12 backend pins and tests
- React/Vite manifest、lockfile、placeholder、build/test
- Docker Compose PostgreSQL 16/backend/frontend definitions and syntax validation
- .env.example and secret boundary
- typed schema、datetime、fare parser、nullable POI、synthetic fixture strategy
- FastAPI health behavior
- stable Make targets、README、audit scripts
- aggregate-only inspection of the supplied CSV

Explicitly out of scope：

- full-data cleaning or quarantine
- Parquet production、time split、soft outlier rules、HDBSCAN
- features A/B/C/D、similar riders、evaluation、model artifacts
- serving migrations、recommendation API、Places/Routes/LLM
- final UI、deployment、brand assets、remote Git operations

## Plan of work

先檢查並保護使用者資料，再建立空 repository 所需的 directories、ignore rules 與 non-secret env example。接著用 stdlib typed boundary 讓 CSV source row 的欄位、時間、fare、數值與 nullable text 能被精確解析；synthetic generator 用來驗證機械行為，不代表真實資料分布。然後建立最小 backend/frontend/Compose stack，讓 liveness 與 database-dependent readiness 的差異可觀察。最後用 Makefile 將 bootstrap、audit、test、dev、安全檢查固定下來，並把所有不能在本機驗證的事項寫入本計畫。完成後停在 Needs review。

## Milestones

### Milestone 1 — Repository discovery and safety baseline

Observable state：local Git metadata exists with no remote or staged files；.gitignore ignores .env、raw CSV/Parquet、generated dependencies and outputs；.env.example has no values；tracking checker exits 0；supplied CSV remains untracked and ignored.

Evidence：mingw32-make safety-check pass；git check-ignore pass；git status --short --branch --ignored shows raw and generated paths as ignored.

### Milestone 2 — Executable data contract

Observable state：SOURCE_FIELDS exact 14-field tuple；TripRecord and FareRange typed dataclasses；time/fare/nullable POI/error behaviors are covered；synthetic generator produces 1,000 parseable rows.

Evidence：pipeline tests 6 passed；data-audit exact header/row count and zero Phase 0 rejects.

### Milestone 3 — Minimal local stack

Observable state：Compose syntax passes；frontend build passes；FastAPI liveness is independent of DB；readiness returns safe 503 without DB and 200 with healthy PostgreSQL. Docker-backed 200-ready path is verified.

Evidence：direct FastAPI live 200 and ready 503; Docker Compose postgres healthy, frontend 200, live 200, ready 200; frontend Vitest 1 passed and Vite build passed; docker compose config --quiet passed.

### Milestone 4 — Stable verification and handoff

Observable state：bootstrap, data-audit, test, safety-check and dev targets are documented; downstream targets return explicit NOT READY non-zero status; README documents setup and non-destructive teardown; roadmap and decisions reflect reality.

Evidence：bootstrap ran twice; Python 10 tests and frontend 1 test plus build passed; plan and roadmap status are Needs review.

## Concrete commands and expected observations

From repository root, with Docker Desktop not required：

- mingw32-make PYTHON=.venv/Scripts/python.exe bootstrap
  Expected and observed: exit 0; first run creates .env, second run keeps existing .env; pinned installs are already satisfied.
- mingw32-make PYTHON=.venv/Scripts/python.exe data-audit
  Expected and observed: exit 0; exact 14-field header, 964991 rows, zero wrong-width rows, zero contract rejects.
- mingw32-make PYTHON=.venv/Scripts/python.exe test
  Expected and observed: exit 0; 10 Python tests passed, 1 Vitest test passed, Vite build passed.
- mingw32-make safety-check
  Expected and observed: exit 0; tracked-file safety boundary passes. Nothing is staged or committed.
- docker compose config --quiet
  Expected and observed: exit 0.
- mingw32-make PYTHON=.venv/Scripts/python.exe dev
  Expected and observed after Docker Desktop starts: services start. The permanent DATABASE_URL_DOCKER setting is used by the backend container.
- Direct local uvicorn check
  Expected and observed: /health/live HTTP 200; /health/ready HTTP 503 with DB_UNAVAILABLE when PostgreSQL is absent.
- Downstream placeholders
  Expected and observed: non-zero NOT READY; no Phase 1+ work is silently claimed.

## Validation and acceptance

Phase 0 evidence is complete and the gate is Needs review.

- [x] Pinned backend/frontend dependency manifests exist; Python 3.12 venv install and npm install completed; frontend package-lock exists.
- [x] Frontend, backend and PostgreSQL start together: Docker-backed liveness/readiness both return 200 after using the correct internal PostgreSQL hostname.
- [x] Data schema、datetime、fare、config、health tests pass: 10 Python tests and 1 frontend test pass.
- [x] Synthetic 1,000-row contract path is deterministic and contains no real rider lookup.
- [x] Raw CSV、.env、API keys、real rider mappings and generated sensitive artifacts are not tracked; ignore and safety checks pass.
- [x] README explains bootstrap、test、startup、health endpoints and non-destructive teardown.
- [x] ROADMAP、DECISIONS and this living plan reflect observed reality.
- [x] No Phase 1 command or implementation was started.

Docker-backed startup、health and frontend checks are now complete. Phase 0 is Completed and this file is ready to be archived after the approved transition.

## Idempotence and recovery

bootstrap only copies .env.example when .env is absent and never overwrites an existing .env. It creates required directories with exist-ok behavior. npm install and pip install are repeatable. docker compose down is the documented non-destructive stop; docker compose down -v is not run automatically and should only be used by a developer who explicitly wants to remove local database volume.

If dependency resolution fails, keep manifests and logs; do not delete caches or broad directories. If ports conflict, use POSTGRES_PORT、BACKEND_PORT、FRONTEND_PORT overrides. If Docker is unavailable, use direct FastAPI tests and record the Compose gap. Do not move or duplicate the supplied raw CSV.

## Interfaces and artifacts

- backend/app/main.py: /health/live and /health/ready.
- backend/app/config.py and backend/app/health.py: environment boundary and PostgreSQL check.
- pipeline/cleaning/contract.py: SOURCE_FIELDS, TripRecord, FareRange, parser and ContractError.
- pipeline/tests/fixtures/synthetic.py: synthetic 1,000-row generator.
- frontend/package.json and frontend/package-lock.json: pinned frontend environment.
- frontend/src/App.tsx and frontend/src/test/App.test.tsx: Phase 0 page and smoke test.
- docker-compose.yml, backend/Dockerfile, frontend/Dockerfile: local services.
- Makefile, scripts/bootstrap.py, scripts/data_audit.py, scripts/check_tracking.ps1, scripts/phase_not_ready.py: stable commands and guards.
- README.md, .env.example, .gitignore: developer and privacy boundaries.
- No bulky test logs, raw CSV copies, or provider responses are committed.

## Handoff

Fresh-session first action：讀 AGENTS.md、docs/exec-plans/ROADMAP.md、本計畫、docs/PROJECT_SPEC.md 相關 sections、docs/ARCHITECTURE.md、docs/DECISIONS.md，再跑 git status --short --branch --ignored。

Handoff action：本計畫已獲使用者批准，移動到 completed/；建立並執行新的 Phase 1 active plan。Phase 1 只處理 cleaning、quality report、split 與 Parquet，不開始 clustering 或 recommendation。

在 reviewer approval 前，不能清理 raw CSV、建立 Parquet、執行 clustering 或開始 Phase 1。

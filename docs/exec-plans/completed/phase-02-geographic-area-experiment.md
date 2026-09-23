# Phase 2 geographic-area experiment: Train-only area candidates

## Purpose and observable outcome

建立可重跑的地理區域實驗，讓審查者能比較：

- 只使用 model_eligible=true 的 Train 座標
- 使用所有 Train 座標，包含 soft-outlier

兩條線在 50,000、100,000、200,000 個分層樣本，以及規格要求的 HDBSCAN 參數網格下的差異。輸出每個候選的 cluster 數、noise ratio、cluster size、等效半徑、城市覆蓋、執行時間與 peak memory，並產出台北、台中、高雄的靜態檢查圖。

本階段只建立 area model 與實驗證據，不建立推薦特徵、相似乘客、排序、資料庫 loader、Places、Routes、LLM 或正式 API。

目前狀態：Completed for Taipei Demo scope（2026-09-19）；72/72 HDBSCAN candidates 已於 2026-09-18 完成。使用者核准台北 Demo 進入 Phase 3；全台泛化、高雄調參與正式 production area model 仍 deferred。

## Progress

- [x] 2026-09-18T13:29:03Z，使用者核准 Phase 1：保留 soft-outlier、第一版模型暫不使用，允許開始 Phase 2。
- [x] 2026-09-18T13:29:03Z，建立 Phase 2 active plan，將納入／排除 soft-outlier 比較列為第一個實驗。
- [x] 2026-09-18T13:46:00Z，安裝並固定 HDBSCAN 0.8.40、scikit-learn 1.6.1、NumPy 2.3.3、Matplotlib 3.10.6、psutil 7.0.0。
- [x] 2026-09-18T13:46:00Z，建立 Train-only、pickup+dropoff coordinate pool 與 deterministic stratified sampler，純函式測試 5 passed。
- [x] 2026-09-18T13:52:44Z，完成兩種 policy、三種樣本大小與 HDBSCAN 參數網格：72/72 candidates completed，0 failed，0 skipped。
- [x] 2026-09-18，assignment smoke test 通過：兩種 policy 都以 Train fit、同一個 preview model 標記 pickup/dropoff、Validation/Test，fit_refit_for_assignment=false。
- [x] 2026-09-18，產出 phase2_report.json、phase2_report.md、phase2_manifest.json 與兩張 200k preview maps；canonical metrics hash 已記錄，完整同設定 rerun 尚未執行。
- [x] 2026-09-19，使用者核准以台北 Demo 範圍進入 Phase 3；先固定 eligible_only 與 250/25/eom 作為 demo baseline，並要求未分群點有 deterministic fallback。全台正式參數選擇與 H3/DBSCAN fallback 延後。

## Surprises and discoveries

- Phase 1 的 clean Parquet 有 964,991 筆，Train 有 452,333 筆；model_eligible Train 有 451,618 筆。兩條 policy 的座標池差異很小，但不能僅用占比推論分群結果一定相同。
- Phase 1 已保留 pickup_lat、pickup_lng、dropoff_lat、dropoff_lng、split、model_eligible 與 pickup_region，可直接重用，不需重新解析 raw CSV。
- 已安裝並固定 HDBSCAN 0.8.40、scikit-learn 1.6.1、NumPy 2.3.3、Matplotlib 3.10.6、psutil 7.0.0。HDBSCAN 0.8.40 與 scikit-learn 1.9.1 不相容，曾在 smoke test 觸發 force_all_finite TypeError；固定到 1.6.1 後單一 1,000 點與 smoke runner 均通過。
- HDBSCAN 的 haversine 距離輸入必須是弧度；本計畫會在轉換函式與單元測試中明確驗證。
- HDBSCAN 參數與候選排序是研究假設，不會在本階段自動宣稱最佳參數。報告中的 provisional preview 只服務地圖檢查，仍需人工選擇。1,000 點 smoke test 中 min_cluster_size=250 會全部成為 noise，因此 smoke assignment coverage=0 不能代表正式 50k/100k/200k 結果。
- 正式 preview sensitivity 結果顯示：sample 50k/100k/200k 的 cluster_count_delta 為 3/2/7，noise_ratio_delta 約為 -0.010940/0.005890/-0.001805；200k 的 Kaohsiung coverage_delta 為 -0.226336，不能直接宣稱兩種 soft-outlier policy 沒有明顯差異。

## Paired soft-outlier diagnostic (2026-09-19)

配對診斷隔離了抽樣差異：從同一批 200k eligible-only Train endpoints fit `250/25/eom`，再只加入 1,430 個 soft-outlier endpoints。對相同的 41,944 個 Kaohsiung eligible endpoints，coverage 由 69.1255% 降至 54.5680%（-14.5576 個百分點），6,142 個點由已分群變成 noise、36 個由 noise 變成已分群；台北變化 +0.6155 個百分點，台中 -0.3040 個百分點。原始 22.6336 個百分點差異有一部分來自兩條 policy 使用不同抽樣池，但高雄敏感度本身仍存在。

參數網格顯示 `250/25/eom` 的高雄差異不是所有設定都會出現：200k 的 `100/10/eom` 在 eligible-only/all-train 的高雄 coverage 為 59%/60%，但約有 484–508 個群集；`500/25/eom` 約為 79%/70%，但只有 38–39 個、等效半徑約 4.1–4.3 km，可能過度合併。這兩組可作為下一輪人工取捨候選，不代表已選定。

## Decision log

- Decision: Phase 2 同時執行 eligible_only 與 all_train 兩條 policy。Rationale: 使用者已核准以納入／排除 soft-outlier 的分群敏感度作為進入後續模型前的必要證據。Date: 2026-09-18. Human approval already granted for the comparison; final policy still requires evidence review.
- Decision: 座標池由 Train 的 pickup 與 dropoff 組成；Validation 與 Test 不可參與 fit。Rationale: PROJECT_SPEC.md section 10.3 要求同一套 area model 能標記兩種端點，且所有模型 fit 只能看 Train。Date: 2026-09-18.
- Decision: 先使用 50k、100k、200k deterministic stratified samples，不直接假設全量 HDBSCAN 可行。Rationale: 先量測時間與 memory，再決定是否使用 approximate_predict 或 fallback。Date: 2026-09-18.
- Decision accepted for Taipei Demo scope: eligible_only with 250/25/eom is the demo baseline; soft-outliers remain retained but excluded from fitting, and unassigned Taipei points need a deterministic fallback. All-city parameter selection remains deferred.

## Outcomes and retrospective

2026-09-18 實驗結果：兩種 policy 都完成 50k、100k、200k 與 12 組 eom candidates，共 72/72 completed。eligible_only 使用 903,236 個 Train endpoints，all_train 使用 904,666 個 Train endpoints。preview assignment coverage（pickup/dropoff）為 eligible_only Train 0.734/0.698、Validation 0.640/0.628、Test 0.678/0.668；all_train Train 0.793/0.762、Validation 0.671/0.696、Test 0.719/0.719。candidate 報告顯示群數與 noise ratio 多數接近，但 200k preview 的 Kaohsiung coverage 差異為 -0.226336，Phase 2 不能直接結案，需人工檢查地圖並決定是否採 eligible_only、all_train 或 dimension-specific policy。完整同設定 rerun 與正式參數選擇仍未完成。

後續必須記錄：

- 實際依賴版本、每個 sample/policy/parameter 的時間與 peak memory。完整 72-candidate runner 約執行 85 分鐘；最高記錄 peak RSS 約 2,759 MB。
- candidate report、assignment report、maps、manifest 與內容 hash。
- eligible_only 與 all_train 在 cluster count、noise ratio、size/radius、城市覆蓋的差異。
- 哪個參數組合獲得人工接受，或為何提出 H3/DBSCAN fallback。
- 未完成項目與對 Phase 3 的限制。

- 實際依賴版本、每個 sample/policy/parameter 的時間與 peak memory。完整 72-candidate runner 約執行 85 分鐘；最高記錄 peak RSS 約 2,759 MB。
- candidate report、assignment report、maps、manifest 與內容 hash。
- eligible_only 與 all_train 在 cluster count、noise ratio、size/radius、城市覆蓋的差異。
- 哪個參數組合獲得人工接受，或為何提出 H3/DBSCAN fallback。
- 未完成項目與對 Phase 3 的限制。

## Context and orientation

輸入與既有真相來源：

- Input: data/processed/trips_clean.parquet
- Phase 1 evidence: data/reports/quality_report.json and data/reports/run_manifest.json
- Source constraints: docs/PROJECT_SPEC.md sections 10.1, 10.2, 10.3, 18.1 and 19
- Architecture boundaries: docs/ARCHITECTURE.md; pipeline code may read processed data, backend must not fit models at request time
- Decision history: docs/DECISIONS.md, especially D-002, D-006 and D-007

重要名詞：

- Coordinate pool：把每筆行程的上車點與下車點都放進同一個座標集合。
- HDBSCAN：依地理密度找出區域的分群方法，也會把密度不足的點標成 noise。
- Noise ratio：被標成 noise 的點占全部點的比例。
- Equivalent radius：用群組內點到中心的距離摘要估算區域大小，不是行政區邊界。
- approximate_predict：用已經 fit 好的 HDBSCAN model 給新座標貼標籤，不重新訓練。

固定限制：

- 只用 Train fit area model；不得把 Validation 或 Test 混入 fit。
- 緯度、經度以 degrees 儲存，送入 haversine HDBSCAN 前轉 radians。
- 測試 min_cluster_size 50、100、250、500；min_samples 10、25、50；cluster_selection_method 至少 eom，必要時才加 leaf。
- 不使用 k-means 代替 HDBSCAN，不在沒有報告的情況下改用其他分群。
- 報告只輸出 aggregate metrics，不輸出 RiderId、TripId、POI 原文或 raw rows。
- 不能把 provisional preview 當成已接受的正式 area model。

## Scope

In scope:

- pinned clustering dependencies
- streaming read of Phase 1 clean Parquet
- Train pickup/dropoff coordinate pool
- deterministic stratified sampling at 50k/100k/200k
- eligible_only versus all_train HDBSCAN experiments
- candidate metrics, runtime, peak memory and reproducibility hashes
- same-model pickup/dropoff and Validation/Test assignment checks
- Taipei, Taichung and Kaohsiung static map checks
- Phase 2 tests, Makefile entry, README command documentation and this plan

Explicitly out of scope:

- area attraction A, similar-rider B, personal mobility C, context D
- evaluation metrics or Test-fit artifacts
- database migrations or serving loader
- recommendation API, Places, Routes, LLM and frontend flow
- final selection without human review
- deployment, public release, remote Git operations or PR creation

## Plan of work

先補上固定版本依賴與單元測試，再建立不依賴 HDBSCAN 的座標、弧度、分層抽樣與 metric helper。這讓資料讀取與數學邊界可以先驗證，避免昂貴實驗才發現單位錯誤。

接著從 clean Parquet 只讀取必要欄位，依 split=train 建立 pickup+dropoff pool。對每個 policy 以 region stratification 和固定 hash 順序抽樣；同一 policy 的 50k 是 100k 與 200k 的 prefix，便於比較樣本大小，而不是每次重新抽出不同資料。

然後執行 HDBSCAN grid。每次 fit 記錄開始前後的 process RSS，並在輸入點已轉弧度的情況下使用 metric=haversine。候選標籤只在 report 中保存 aggregate metrics；必要的 provisional labels 只放在 ignored local output 用來畫圖或 assignment smoke test。

最後對每個 policy 的 provisional preview model 做 pickup、dropoff、Validation、Test assignment smoke test，確認 fit 只發生一次。輸出候選表、差異摘要、地圖、manifest 與重跑 hash。若資源不足，保留已完成的 bounded evidence，提出 H3 或 DBSCAN fallback，不把未完成的實驗寫成結論。

## Milestones

### Milestone 1 — Dependencies and deterministic geometry helpers

Observable state: pinned dependencies install; haversine degree-to-radian conversion, region stratification, sample sizes and deterministic ordering have unit tests.

Acceptance: Python tests pass; converting known degree coordinates produces expected radians; same input/config/seed produces the same sampled coordinate hashes.

### Milestone 2 — Bounded HDBSCAN candidate grid

Observable state: eligible_only and all_train each produce candidate rows for 50k, 100k and 200k samples, with required parameter combinations and runtime/peak RSS measurements.

Acceptance: report contains cluster count, noise ratio, cluster-size summaries, equivalent radius, Taipei/Taichung/Kaohsiung coverage, runtime and peak memory for each completed candidate. Any failed or skipped candidate is recorded with an error or resource reason.

### Milestone 3 — Assignment and visual inspection

Observable state: one fit model can assign both pickup and dropoff points and can assign Validation/Test coordinates without refitting. Static maps show Taipei, Taichung and Kaohsiung checks for each policy's provisional preview.

Acceptance: assignment report records fit split=train, fit point count, assigned point counts and assignment coverage; no Validation/Test coordinates are used in fit; map files exist and do not contain identifiers.

### Milestone 4 — Review package and handoff

Observable state: aggregate JSON/Markdown report, map images, manifest, content hashes and plan evidence are inspectable under ignored data/clustering/phase2.

Acceptance: rerun with same input/config reproduces canonical report and coordinate/metric hashes; Phase 2 plan is set to Needs review; roadmap remains at Phase 2 until a human selects a candidate or approves a fallback. Phase 3 is not started.

## Concrete commands and expected observations

From F:/Project/Hotai-Hackathon:

- mingw32-make PYTHON=.venv/Scripts/python.exe bootstrap
  Expected: pinned pipeline dependencies install and existing .env is preserved.
- mingw32-make PYTHON=.venv/Scripts/python.exe test
  Expected: Phase 1 and Phase 2 unit tests pass, frontend test/build remain green.
- mingw32-make PYTHON=.venv/Scripts/python.exe cluster-experiments
  Expected: exit 0 when the complete bounded experiment finishes; output points to data/clustering/phase2/phase2_report.json and phase2_report.md. It must not print row values or IDs.
- Get-Content data/clustering/phase2/phase2_report.md
  Expected: human-readable policy comparison, candidate metrics, resource observations, assignment coverage and limitations.
- Get-Content data/clustering/phase2/phase2_manifest.json
  Expected: input artifact hash, configuration, dependency versions, completed/failed candidate counts and output hashes, without raw identifiers.
- mingw32-make safety-check
  Expected: generated phase2 outputs remain ignored and tracking boundary passes.

The experiment may run longer than a normal unit test. If it returns a running process, poll the same process rather than starting a second run. Do not delete the raw CSV or broad data directories to recover.

## Validation and acceptance

The checklist below still records deferred all-city evidence. The Taipei Demo scope is accepted under D-008; deferred items are not production claims or blockers for the scoped demo.

Phase 2 cannot be marked complete for all-city generalization until all of the following are true:

- [x] Phase 1 approved and D-007 recorded.
- [x] Input is the Phase 1 clean artifact with matching content hash.
- [x] Fit uses Train only and includes pickup and dropoff coordinates.
- [x] Both soft-outlier policies are compared at 50k, 100k and 200k.
- [x] Required HDBSCAN grid is run: 72/72 completed, 0 failed, 0 skipped.
- [x] Metrics include cluster count, noise ratio, size distribution, equivalent radius, city coverage, time and peak memory.
- [x] Assignment proves one model can label pickup, dropoff, Validation and Test without refit.
- [x] Taipei, Taichung and Kaohsiung visual checks are generated in both policy maps; visual human review remains pending.
- [ ] Same input/config rerun produces matching canonical metrics and hashes; one completed run has canonical metrics hash ca1bfbb397f1f9766bc735658509159e09c5b4908aa1d9090a0a7ec432a34d5b, but a second full run is still pending.
- [x] No raw identifiers or provider responses enter reports or tracked files; safety-check passed with 0 tracked files.
- [ ] Human selects a parameter set or approves a documented fallback.
- [x] Phase 3 has not started.

## Idempotence and recovery

All outputs go under data/clustering/phase2, which is ignored. The runner writes a run-specific temporary directory inside that output root, validates report and hashes, then replaces only the named phase2 report artifacts. It never modifies data/processed/trips_clean.parquet or the raw CSV.

If a candidate fit fails, record the candidate as failed with a bounded error class and continue when safe. If memory rises above the configured budget, stop the current fit, preserve completed candidate evidence, and mark the remaining candidates blocked by resource use. Do not silently substitute a smaller sample or different algorithm.

If a rerun is interrupted, remove only the explicitly named data/clustering/phase2/.run-* directory after confirming it is inside data/clustering/phase2, then rerun with the same config. Do not use recursive deletion against data or the repository root.

## Interfaces and artifacts

- pipeline/clustering/geometry.py: radians, haversine, region and deterministic sampling helpers.
- pipeline/clustering/experiments.py: Parquet loading, HDBSCAN fit, metrics, assignment and report writing.
- pipeline/tests/test_clustering.py: pure helper and determinism tests.
- scripts/cluster_experiments.py: stable command entry point.
- pipeline/requirements.txt: pinned Phase 2 dependencies.
- Makefile cluster-experiments: invokes scripts/cluster_experiments.py.
- data/clustering/phase2/phase2_report.json: aggregate candidate and assignment evidence.
- data/clustering/phase2/phase2_report.md: human-readable review package.
- data/clustering/phase2/phase2_manifest.json: input/config/dependency/output hashes.
- data/clustering/phase2/maps/*.png: static city checks.
- No RiderId, TripId, raw row, POI text or provider response is written to reports or maps.

## Handoff

Fresh-session first action: read AGENTS.md, docs/exec-plans/ROADMAP.md, this plan, docs/PROJECT_SPEC.md sections 10.1–10.3 and 18.1, docs/ARCHITECTURE.md, docs/DECISIONS.md; then run git status --short --branch --ignored.

First incomplete action: review the Phase 2 sensitivity report and maps, then decide whether the 200k Kaohsiung coverage difference requires a dimension-specific policy or a rerun before selecting parameters.

When the candidate report exists, stop at Needs review and present the included-versus-excluded comparison plus the resource evidence for human parameter selection. Do not start Phase 3 until that review is explicitly approved.

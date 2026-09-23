# Phase 3 Taipei Demo slice: deterministic features and recommendation baseline

## Purpose and scope

建立一條可展示、可重跑、可解釋的台北 Demo 推薦路徑。這不是全台 production model；它是在已核准的台北範圍內，先完成最小可用的 area features、deterministic ranking 與 demo evidence。

目前狀態：Completed（2026-09-20T16:35:38Z）；已完成 Taipei area artifact、aggregate features、個人化、鎖定評估與可操作 mock UI。依使用者授權，Agent review 已完成；Phase 4 可使用 D-009 鎖定的 A+C serving baseline。


## Progress

- 2026-09-20T20:37:45+08:00 — M1 Completed：使用 Phase 2 核准的 eligible_only、Train-only、200k deterministic sample、HDBSCAN 250/25/eom，產出 102 個 Taipei verified areas；sample digest 與 Phase 2 approved candidate 一致。
- 2026-09-20T20:37:45+08:00 — M2 Completed：產出 1,020 筆 Taipei aggregate feature rows，包含 smoothing、Train p5/p95 normalization、coverage 與 fallback 統計；輸出不含 RiderId、TripId 或 raw rows。
- 2026-09-20T20:37:45+08:00 — M3 Completed：完成 deterministic area ranking、Origin-Period Popularity baseline、score breakdown 與 verified/fallback demo evidence。
- 2026-09-20T20:37:45+08:00 — M4 Completed：完成 Validation smoke report；未使用 Test。Validation Taipei destination coverage 約 0.634197；Origin-Period Popularity HitRate@5 約 0.342970，A-only 約 0.173109，因此目前不宣稱 A-only 優於強基準。
- 2026-09-20T23:12:00+08:00 — M5 Completed：完成 390×844 mobile-first mock UI、三種 persona、位置選擇、Top 5、fallback 標示、技術依據、模擬叫車與可恢復錯誤；餐廳資料明確標示為合成展示資料。Vitest 4 tests 與 production build 通過，headless Edge DevTools 390×844 視覺檢查通過並修正初版 viewport 裁切。
- 2026-09-20T16:35:38Z — M6 Completed：personalization v3 與 personalized evaluation v2 已完成。Validation 依 HitRate@5、MRR 與較簡單模型的 tie-break 選定 A+C（A=0.30、C=0.70），再執行鎖定後 Test；Test A+C HitRate@5=0.4828、MRR@5=0.3866，勝過 Origin-Period Popularity 的 0.3863、0.2450。B 無驗證增益，依 D-009 預設停用；full/light/cold cohort 均保留報告，不能宣稱 cold 個人化提升。
- 2026-09-21T00:18:48+08:00 — M6 review correction：第一版 personalized evaluation 因獨立 Luna high 審查發現 DistanceFit 未使用 p75 而作廢，不得作為模型結論。已依規格修正為 p25–p75 plateau、p75–p90 下降，加入 p75/reweight/candidate/metric tests，並產生 personalization v3。接下來的 v2 evaluation 是一次明確記錄的 implementation-bug rerun；舊 v1 report 保留在 ignored local output 供追溯。
- 2026-09-20T16:35:38Z — 驗證完成：完整 make test 通過（Python 31 tests、frontend 4 tests/build）；safety-check 通過；評估 JSON 沒有 raw rider/trip identifier 欄位；data/features/phase3_taipei 已被 Git 忽略。
- 下一步：封存本計畫，建立 Phase 4 database/API 的唯一 active plan。
## Approved baseline

- Demo city: Taipei only.
- Area baseline: eligible_only；只使用 model_eligible=true 的 Train 資料 fit。
- Area parameters: HDBSCAN 250/25/eom，作為 demo baseline，不宣稱 production optimal。
- Soft-outliers: 保留在 clean artifacts 與 reports，不納入第一版 model fitting。
- Unassigned points: 使用 deterministic fallback；不可把 noise 當成已驗證的區域。
- Generalization: 不對 Taichung、Kaohsiung 或全台做 production claim。

## Required invariants

- 所有模型 fit 只能使用 Train；Validation 用來選擇設定，Test 只有在設定鎖定後才可使用。
- 排名必須 deterministic；LLM 不得決定排序。
- 報告與輸出不得含 RiderId、TripId、raw rows、POI 原文或 restricted provider response。
- Area model 不在 request time fit；後端只讀取可追溯的 demo artifact。
- Demo UI 必須把 fallback、模擬資料與歷史估計清楚標示。

## Milestones

### Milestone 1 — Freeze Taipei demo area artifact

Observable state: 產出帶有 input hash、policy、參數與版本的 Taipei demo area artifact；確認 Train fit 與 deterministic prediction。

Acceptance: 同一 input/config/seed 產生相同 aggregate hash；未分群點能走 deterministic fallback。

Progress: Completed（2026-09-20）。正式 artifact 使用 200k sample digest b589b2a59c6a...，102 個 verified Taipei areas；同設定重用產生相同 model_version/artifact_hash。

### Milestone 2 — Build Taipei aggregate features

Observable state: 以 approved area artifact 產生台北區域的可追溯 aggregate features，不輸出 raw rider/trip identifiers。

Acceptance: feature pipeline 有 Train fit/Validation transform 邊界；缺資料區域有明確的 zero/smoothing/fallback 行為。

Progress: Completed（2026-09-20）。產出 1,020 rows 的 aggregate feature artifact，使用 Train eligible rows，並記錄 smoothing、p5/p95 normalization 與 fallback coverage。

### Milestone 3 — Deterministic recommendation baseline

Observable state: 固定 Demo persona 與輸入位置可以回傳固定排序、分數拆解與 evidence。

Acceptance: 重複相同 request 結果一致；排序不依賴 LLM 或外部服務；至少涵蓋台北密集區與一個 fallback 情境。

Progress: Completed（2026-09-20）。demo_evidence.json 包含 verified-area 與 fallback-area 兩種情境，排序含 score breakdown 與 aggregate evidence。

### Milestone 4 — Taipei offline smoke evidence

Observable state: 報告台北 Demo baseline 的候選 coverage、fallback rate、基本 ranking evidence 與限制。

Acceptance: 不宣稱全台 generalization；若使用 Test，只能在設定鎖定後執行一次並明確標示 scope。

Progress: Completed（2026-09-20）。Validation smoke 已產出；Test 未使用，報告明確標示 Taipei scope 與 coverage limitation。

### Milestone 5 — Mock UI handoff

Observable state: 前端可完成台北 Demo 的選點、推薦結果與說明流程，並能在無外部 provider/LLM 時完成。

Acceptance: make test、必要的 demo checks 與 secret/raw-data safety checks 通過；文件包含兩分鐘 Demo 操作說明。

Progress: Completed（2026-09-20）。UI 在無 backend、provider 與 LLM 時可完成 HOME、LOCATION_SELECTION、RECOMMENDING、RESULTS、RESTAURANT_DETAIL、RIDE_CONFIRMATION 與 ERROR 流程；fallback 與合成資料有清楚標示。Vitest 4 tests、production build 與 390×844 screenshot QA 通過。

### Milestone 6 — Taipei personalization and locked evaluation

Observable state: Train-only rider profile、B similarity 與 C mobility features 可重跑產生；Validation 比較 Global、Origin、A、A+C、A+B、A+B+C，鎖定最簡單且有證據的模型後才執行一次 Test。

Acceptance: B 只對 Train trip_count >= 10 啟用且有效鄰居少於 5 時為 unavailable；C 依 full/light/cold 規則降級；所有 component 在 0–1；Validation 選擇的權重與 enablement 被記錄；Test 不參與選擇；報告保留 destination coverage 與各 persona cohort，不含 RiderId 或 raw rows。

Progress: Completed（2026-09-20T16:35:38Z）。輸出 personalized_evaluation_v2 JSON/Markdown；舊 v1 評估因實作缺陷作廢但保留於 ignored local output 供稽核。已鎖定 A+C，B 預設 unavailable。

## Explicitly deferred

- 高雄 soft-outlier 敏感度的正式解法。
- H3、DBSCAN 或其他 all-city fallback 的正式比較。
- 城市別分群參數與全台 production area model。
- 完整六模型 all-city offline evaluation。
- Google Places、Routes、LLM 與正式 deployment；除非後續 phase plan 明確納入。

## First incomplete action

Phase 3 Taipei scope 已完成；封存後的下一個動作是建立 Phase 4 active plan，讓 database loader 與 API 使用 D-009 的 A+C locked model。不要重跑高雄或全台分群。


## Surprises and discoveries

- 2026-09-20：Phase 2 approved candidate 的 200k sample digest 與正式 Phase 3 area artifact 一致；Taipei Demo artifact 使用 102 個 verified areas。
- 2026-09-20：正式 feature artifact 的 verified destination coverage 約 0.644048，與 Phase 2 Taipei assignment coverage 約 0.646 相近；fallback 仍是必要行為，不可省略。
- 2026-09-20：第一輪 Validation smoke 只使用 Train fit 與 Validation transform/evaluation，Test 尚未使用；B/C 與完整六模型比較仍標示為限制。
- 2026-09-21：第一版 C 實作把高分 plateau 截到 median，而規格要求 p25–p75；這會直接影響 A+C 結論。獨立審查將其列為 P1，v1 personalized Test report 因此作廢，修正後以新 artifact/report version 重跑並保留審計紀錄。
- 2026-09-21：修正後 v2 Test 仍支持 A+C 勝過 Origin-Period Popularity，但 B 沒有額外增益。full 與 light 的 A+C HitRate@5 分別為 0.6180、0.5361；cold 為 0.1826，且其個人化 component 為 unavailable，不能歸因為個人化改善。

## Decision log

- 2026-09-20：area artifact 固定使用 eligible_only、Train-only、200k deterministic sample、HDBSCAN 250/25/eom；noise 與非 Taipei verified cluster 使用顯式 region fallback，不把 noise 當成正式區域。
- 2026-09-20：以 area attraction A 與 Origin-Period Popularity 作為 Taipei Demo 的 deterministic baseline evidence；Validation 報告只用於 smoke/比較，未用 Test 選參數。
- 2026-09-21：D-009 採用 A+C（0.30/0.70）為 Taipei Demo serving baseline，B 因未通過 Validation 增益門檻停用。

## Outcomes and retrospective

Phase 3 已完成可重跑 Taipei Demo：area metadata、aggregate feature artifact、salted profile、A+C deterministic ranking、B disablement、fallback evidence、locked Validation/Test evaluation 與可操作 mock UI。限制仍是 Taipei-only、destination-area 離線題目與 cold cohort 不具個人化證據；Phase 4 必須維持這些邊界。
## Validation commands

From F:/Project/Hotai-Hackathon:

- mingw32-make PYTHON=.venv/Scripts/python.exe test
- mingw32-make safety-check
- mingw32-make PYTHON=.venv/Scripts/python.exe demo-check

Observed 2026-09-20: Phase 3 area/features/evaluation/demo artifacts generated successfully; demo outputs contain no raw RiderId/TripId fields; fallback is explicit and deterministic. make demo-check remains intentionally NOT READY because it belongs to Phase 8.

## Handoff

Fresh-session first action: read AGENTS.md, docs/exec-plans/ROADMAP.md, this plan, docs/PROJECT_SPEC.md sections 10.1–10.4 and 18.1, docs/ARCHITECTURE.md, docs/DECISIONS.md; then run git status --short --branch --ignored.

Do not reopen all-city Phase 2 or start provider integrations until the Taipei Demo slice has observable evidence and a new scope decision.

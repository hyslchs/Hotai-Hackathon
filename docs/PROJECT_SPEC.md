# yoxi AI 餐廳推薦 Demo：產品與技術規格

版本：1.1  
日期：2026-09-18  
文件用途：定義產品行為、資料限制、演算法、介面與整體完成條件。本文件不記錄執行進度。

執行時先讀根目錄 `AGENTS.md`。跨多小時或跨模組的工作依 `docs/PLANS.md` 建立 ExecPlan；專案分期、依賴與決策關卡以 `docs/exec-plans/ROADMAP.md` 為準；當前狀態只記在 `docs/exec-plans/active/` 的計畫中。

## 1. 執行摘要

本專案要完成一套可實際操作的 yoxi 風格 Demo。使用者從目前位置啟動「今天吃什麼」，系統利用匿名歷史行程推估值得搭車前往的區域，再從外部地點服務取得營業中的餐廳，輸出 Top 5、推薦依據與模擬叫車畫面。

本系統的核心判斷必須由可重現的推薦演算法完成。LLM 只能把結構化依據改寫成自然語言，不能決定排名。真正派車、付款、yoxi 登入與正式票價不在本次範圍。

第一優先不是做完 UI，而是依序證明以下事項：

1. 原始資料能穩定清理，且沒有時間洩漏。
2. 地理群聚能形成合理的城市移動區域。
3. 完整模型在未來時段的離線測試中，至少能與簡單基準公平比較。
4. API 能在外部服務失敗時維持 Demo。
5. 前端能在兩分鐘內完整展示推薦到模擬叫車的流程。

## 2. 規格優先順序

Codex 遇到衝突時，依下列順序判斷：

1. 本文件的資料、安全、驗收與禁止事項。
2. 實際資料檢查結果與自動化測試。
3. `docs/DECISIONS.md` 中已經確認的決策。
4. 簡報及既有示意圖。
5. Codex 自行推測。

現有簡報中的 A、B、C、D 與權重屬於概念示意。實作不得因為要配合示意圖而跳過驗證或硬保留無效模組。

## 3. 已確認的來源資料

### 3.1 原始檔案

- `yoxi_數據資料.csv`
- `欄位說明.docx`
- 兩張同內容的演算法簡報 PNG，實際 SHA-256 相同

### 3.2 實際資料盤點

| 項目 | 已確認結果 |
| --- | ---: |
| 行程筆數 | 964,991 |
| 欄位數 | 14 |
| 不重複乘客 | 132,035 |
| 重複 `Id` | 0 |
| 完全重複列 | 0 |
| 行程開始範圍 | 2026-02-01 00:03:47 至 2026-05-01 00:48:08 |
| 空白上車 POI | 658,225 |
| 空白下車 POI | 656,650 |
| 零行駛距離 | 358 |
| `TravelTime > 180` 分鐘 | 328 |
| `TravelDistance > 200 km` | 30 |
| 推算速度大於 120 km/h | 148 |
| 推算速度小於 1 km/h | 590 |
| 系統時間先後矛盾 | 0 |
| 乘客少於 3 筆 | 65,353 人，87,108 筆行程 |
| 乘客 3 至 9 筆 | 42,109 人，209,763 筆行程 |
| 乘客至少 10 筆 | 24,573 人，668,120 筆行程 |

資料結論：Cold Start 是主要使用情境，不是例外。POI 欄位是自由文字且約三分之二為空，不能把它當成完整餐廳標籤或偏好真值。

### 3.3 欄位契約

| 欄位 | 型別 | 意義 | 清理後欄位 |
| --- | --- | --- | --- |
| `Id` | int64 | 唯一行程編號 | `trip_id` |
| `RiderId` | int64 | 匿名乘客編號 | `rider_id` |
| `OrderStartDateTime_UTC8` | datetime | 行程開始 | `started_at` |
| `OrderEndDateTime_UTC8` | datetime | 行程結束 | `ended_at` |
| `PickUpLatitude` | float | 上車緯度 | `pickup_lat` |
| `PickUpLongitude` | float | 上車經度 | `pickup_lng` |
| `DropOffLatitude` | float | 下車緯度 | `dropoff_lat` |
| `DropOffLongitude` | float | 下車經度 | `dropoff_lng` |
| `TravelTime` | int | 行駛分鐘數 | `travel_time_min` |
| `TravelDistance` | int | 行駛公尺數 | `travel_distance_m` |
| `OrderFormCreatedTime_UTC8` | datetime | 叫車時間 | `ordered_at` |
| `PickUpLocationType` | string nullable | 上車 POI 自由文字 | `pickup_poi_text` |
| `DropOffLocationType` | string nullable | 下車 POI 自由文字 | `dropoff_poi_text` |
| `PaymentTotalRange` | string | 金額區間 | `fare_lower_exclusive`、`fare_upper_inclusive`、`fare_midpoint` |

所有時間解析為 `Asia/Taipei` aware datetime。`[100,200]` 依說明解釋為 101 至 200，因此中點為 `(101 + 200) / 2`。保留原始字串，解析失敗時不得猜值。

## 4. 產品目標與成功定義

### 4.1 目標使用流程

1. 使用者進入地圖首頁。
2. 選擇 Demo 乘客或 Cold Start 身分。
3. 選擇或輸入目前位置與模擬時間。
4. 點擊「今天吃什麼」。
5. 系統產生 Top 5 餐廳與地圖標記。
6. 使用者查看餐廳、推薦依據與車程估算。
7. 點擊「搭 yoxi 前往」進入模擬確認畫面。
8. 系統記錄曝光、點擊與叫車按鈕事件，但不建立真實訂單。

### 4.2 技術成功條件

- 能以完整資料重建處理結果，沒有手動修改產出檔。
- 所有模型與正規化參數只使用訓練期資料擬合。
- 能輸出並比較至少五個 area-ranking baseline。
- API 對未知乘客、資料不足、Places 失敗、LLM 失敗都有可預期結果。
- 排名分數和各 component 均可追溯到 0 至 1 的輸入。
- Google Places 使用明確 FieldMask；外部 API key 不進前端 bundle。
- 在 mock 外部服務時，推薦 API p95 小於 750 ms；串接真實外部服務時目標 p95 小於 4 秒。
- E2E 測試涵蓋完整個人化、Cold Start、Places fallback 與 API 錯誤。

### 4.3 研究與簡報可宣稱的範圍

離線測試只能支持：「歷史移動行為能否預測使用者在特定時間可能前往的區域。」

不得由此宣稱：「系統知道使用者口味」或「使用者一定喜歡推薦餐廳」。餐廳偏好需要後續真人使用測試、點擊、叫車與回饋資料才能驗證。

## 5. 本次範圍

### 5.1 必做

- 資料清理、品質報告與 Parquet 產出
- 時間切割與防資料洩漏測試
- 地理群聚實驗、群聚報告與可視化
- Area attraction、個人移動、相似乘客特徵
- Baseline、權重校準與離線測試
- FastAPI 推薦 API
- PostgreSQL serving schema 與 migration
- Google Places API New 串接
- 可合法使用的本地 fallback 餐廳資料
- React、TypeScript、Vite 地圖介面
- 推薦解釋、模擬車程及叫車確認
- 事件記錄、單元測試、整合測試、E2E 與 Docker Compose

### 5.2 明確不做

- 真實 yoxi 登入、會員資料或派車 API
- 真實付款、訂位或正式車資報價
- 自動訂餐廳、聊天機器人
- Microservices、Kafka、Kubernetes、Redis、Vector DB
- 線上即時重訓、Learning-to-Rank production pipeline
- 以 LLM 直接決定推薦順序
- 將原始 CSV、真實 RiderId、API key 或外部 API 完整回應 commit 到 Git
- 未經授權長期保存 Google Places 的受限欄位或照片資源名稱

## 6. 隱私與安全要求

1. `RiderId` 視為假名化識別碼，不在前端、一般 log、錯誤訊息或截圖中顯示。
2. Demo 使用 `demo_rider_01` 等別名，由後端映射真實資料 ID。
3. 原始資料只存在 `data/raw/`，必須被 `.gitignore` 排除。
4. 產出的 Rider profile 若會離開本機，使用不可逆 salted hash；salt 只由環境變數提供。
5. Recommendation log 不記錄完整歷史，只記 request id、demo rider alias、粗略 geohash 或 area id、排名與互動。
6. Secret 只放 `.env` 或部署平台；repo 僅提供 `.env.example`。
7. CORS 預設只允許本地前端與明確設定的正式網域。
8. Backend 對外部 API 設定 timeout、有限次 retry 與 circuit-breaker-like fallback，不能無限重試。

## 7. 技術架構

| 層 | 技術 |
| --- | --- |
| Frontend | React、TypeScript、Vite、Tailwind CSS |
| 地圖 | Google Maps JavaScript API；無 key 時提供簡化靜態底圖或測試模式 |
| Backend | Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic |
| Serving DB | PostgreSQL 16 |
| Offline analytics | Python、DuckDB、Pandas 或 Polars、Parquet |
| ML | NumPy、scikit-learn、HDBSCAN |
| 外部餐廳 | Places API New，優先 Nearby Search New |
| 道路資訊 | Routes API 可選；未啟用時使用 Haversine 估算 |
| LLM | Provider adapter；功能可關閉；失敗時 deterministic template |
| Test | Pytest、Vitest、Playwright |
| 執行 | Docker Compose；offline pipeline 為一次性 job |

不鎖死套件的假定最新版。Codex 建立 lockfile，記錄實際版本並確保 CI 與 Docker 使用相同版本。

## 8. Repository 目標結構

```text
yoxi-ai-demo/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── map/
│   │   │   ├── recommendations/
│   │   │   ├── restaurants/
│   │   │   └── ride/
│   │   ├── services/
│   │   ├── stores/
│   │   ├── types/
│   │   └── test/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── config/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   └── services/
│   │       ├── recommendation/
│   │       ├── places/
│   │       ├── routes/
│   │       ├── explanation/
│   │       └── ride/
│   ├── migrations/
│   └── tests/
├── pipeline/
│   ├── cleaning/
│   ├── clustering/
│   ├── features/
│   ├── similarity/
│   ├── evaluation/
│   ├── loading/
│   └── tests/
├── data/
│   ├── raw/
│   ├── processed/
│   ├── reports/
│   └── demo/
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── PLANS.md
│   ├── DECISIONS.md
│   └── exec-plans/
│       ├── ROADMAP.md
│       ├── active/
│       └── completed/
├── scripts/
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
├── AGENTS.md
└── README.md
```

## 9. 環境變數

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/yoxi
RAW_DATA_PATH=/data/raw/yoxi_數據資料.csv
PROCESSED_DATA_DIR=/data/processed

# Browser-visible; require Maps JavaScript API and HTTP-referrer restriction.
VITE_GOOGLE_MAPS_BROWSER_API_KEY=
GOOGLE_PLACES_API_KEY=
GOOGLE_ROUTES_API_KEY=

LLM_ENABLED=false
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=

DEMO_MODE=true
DEMO_FALLBACK_ENABLED=true
RIDER_HASH_SALT=
ALLOWED_ORIGINS=http://localhost:5173
LOG_LEVEL=INFO
```

Frontend 只能取得 browser-restricted Maps key。Places、Routes、LLM key 必須留在 backend。

## 10. Offline 資料管線

### 10.1 時間切割

以 `started_at` 切割，禁止 random split：

| Dataset | 範圍 | 實際筆數 |
| --- | --- | ---: |
| Train | `< 2026-03-16 00:00:00` | 452,333 |
| Validation | `>= 2026-03-16` 且 `< 2026-04-01` | 169,934 |
| Test | `>= 2026-04-01` 至資料結尾 | 342,724 |

五月一日凌晨的 40 筆行程保留在 Test，不應因日曆邊界遺漏。所有 scaler、群聚模型、相似乘客、熱門度與權重選擇只能看 Train；Validation 用於參數和權重選擇；Test 只在設定鎖定後跑一次。

正式 Demo 可在評估完成後，以全資料重建 serving artifacts，但必須保留 evaluation artifacts，不能用全資料結果回寫測試成績。

### 10.2 清理策略

輸出 `trips_clean.parquet` 與 `trips_quarantine.parquet`。原始列永不覆寫。

Hard invalid，預設排除：

- 必要欄位無法解析
- 重複 trip id
- `ended_at < started_at`
- `ordered_at > started_at`
- 經緯度超出合理台灣範圍：緯度 20 至 27、經度 118 至 123
- `travel_time_min <= 0`
- `travel_distance_m < 0`
- fare range 無法解析

Soft outlier，預設排除模型訓練但保留報告：

- `travel_distance_m == 0`
- 推算速度 `< 1 km/h` 或 `> 120 km/h`
- `travel_time_min > 180`
- `travel_distance_m > 200,000`
- `abs((ended_at-started_at) - TravelTime) > 2` 分鐘

Soft outlier 門檻是初始規則。Codex 必須輸出各規則單獨與聯集筆數、分城市與日期分布，再決定是否維持；不得靜默刪除。

必要衍生欄位：

- `weekday_class`: `weekday` 或 `weekend`
- `period`: `morning` 05:00–10:59、`lunch` 11:00–13:59、`afternoon` 14:00–16:59、`dinner` 17:00–20:59、`night` 21:00–04:59
- `distance_km`
- `elapsed_time_min`
- `speed_kph`
- `fare_midpoint`
- `model_eligible`
- `exclusion_reasons`
- `split`

### 10.3 地理區域群聚

同一套 area model 要能標記 pickup 與 dropoff，才能計算來源多樣性與跨區比例。只用 Train 座標擬合，Validation 與 Test 用 prediction 或最近 cluster 指派。

不得一開始就把某組 HDBSCAN 參數寫死。先執行實驗：

1. 由 Train 的 pickup 與 dropoff 組成座標池。
2. 先以 50k、100k、200k 的地理分層樣本測試記憶體與時間。
3. 測試至少以下候選：
   - `min_cluster_size`: 50、100、250、500
   - `min_samples`: 10、25、50
   - `cluster_selection_method`: `eom`，必要時比較 `leaf`
4. 使用 haversine 距離時，所有公里參數必須轉為弧度，並有單元測試。
5. 輸出每組參數的 cluster 數、noise ratio、cluster size 分布、等效半徑、城市覆蓋、執行時間與 peak memory。
6. 產出台北、台中、高雄三區的互動或靜態檢查圖。

初始品質參考而非強制答案：noise ratio 5% 至 35%、多數城市 cluster 等效半徑約 0.3 至 3 km、p90 不應大於 8 km。最後參數要在 `DECISIONS.md` 留下數據與選擇理由。

若全量 HDBSCAN 不可行，允許以地理分層樣本擬合後 `approximate_predict`；不得未回報就改成 k-means。若 HDBSCAN 經實驗仍無法形成合理區域，停止於決策關卡，提出 H3 或 DBSCAN fallback 及其取捨。

## 11. 推薦演算法

所有 component 在加權前都要是 0 至 1。正向數值使用 Train 的 p5/p95 robust min-max：`clip((x-p5)/(p95-p5),0,1)`；高度偏態的 count 先 `log1p`。Validation 與 Test 不重新擬合 scaler。分母為零或 component 缺失時，必須記錄原因並重新正規化剩餘權重。

### 11.1 A 區域移動吸引力

```text
A = 0.30 × VisitHeat
  + 0.25 × PeriodLift
  + 0.15 × CrossAreaRatio
  + 0.15 × SourceDiversity
  + 0.15 × ReturnRate
```

- `VisitHeat`: 該 area、period、weekday_class 的每日平均到訪數，先 `log1p` 再 scale。
- `PeriodLift`: `P(destination=area | period, weekday_class) / P(destination=area)`，加平滑後取 log 再 scale。這用來降低交通樞紐全天高流量造成的霸榜。
- `CrossAreaRatio`: 前往 area 且 pickup area 不同的行程占比；noise pickup 不列入分母。
- `SourceDiversity`: pickup area 分布的 normalized entropy，`H / log(K)`；來源少於兩個時為 0。
- `ReturnRate`: 到訪該 area 至少兩次的 rider 數除以所有到訪 rider 數。

所有比例採 Laplace 或 empirical-Bayes smoothing，平滑常數由 Validation 選定並記錄。

### 11.2 B 相似乘客探索

只對 Train 歷史至少 10 筆的 rider 啟用。

數值特徵：

- median distance、p75 distance、median duration
- lunch、dinner、night、weekend ratio
- cross-area ratio
- fare midpoint mean

區域特徵：`log1p(rider-area visit_count)` 的 sparse vector，可用 TF-IDF 降低超熱門區域的支配。數值 block standardize 後 L2 normalize；area block L2 normalize；初始以 0.6 與 0.4 合併。Block 權重需在 Validation 比較。

使用 cosine similarity，排除自己，預算 Top 50 neighbors。不得在第一版導入 ALS、LightFM 或 Vector DB。

```text
B(u,a) = Σ max(sim(u,v),0) × log(1 + visits(v,a,period))
         ─────────────────────────────────────────────
                   Σ max(sim(u,v),0)
```

結果再依 Train scaler 轉為 0 至 1。若有效 neighbor 少於 5，B 視為 unavailable，而不是 0 分。

### 11.3 C 個人移動適配度

```text
C = 0.50 × DistanceFit
  + 0.20 × TimeHabitFit
  + 0.15 × WeekdayFit
  + 0.15 × PersonalAreaAffinity
```

- `DistanceFit`: 比較目前位置到 area centroid 的估計道路距離與 rider 的 p25、median、p75、p90。p25 至 p75 為高分，超過 p90 後快速下降；不可單純設定越近越高。
- `TimeHabitFit`: rider 在該 period 的平滑後搭乘傾向。
- `WeekdayFit`: rider 在 weekday 或 weekend 的平滑後搭乘傾向。
- `PersonalAreaAffinity`: rider 過去對該 area 的 `log1p(visit_count)` 正規化值，權重不可提高到壓制探索。

3 至 9 筆行程可計算簡化 C。缺少可靠 p25/p90 時，改用 median 與全體同級 rider 分布，不可偽造個人分位數。

### 11.4 個人化層級

```text
trip_count >= 10:
AreaScore = wA × A + wB × B + wC × C
初始值 0.40 / 0.30 / 0.30

trip_count 3–9:
AreaScore = 0.55 × A + 0.45 × C

trip_count < 3 或未知 rider:
AreaScore = A
```

0.40/0.30/0.30 只是 hypothesis。Validation 上以 0.1 為步長做 constrained grid search，`wA+wB+wC=1` 且 `wA>=0.3`。選定後鎖定，Test 只能執行一次。若 B 沒有提升，應刪除或停用，不得為了簡報保留。

### 11.5 地理候選過濾

1. 先用 Haversine × 1.30 估計道路距離。
2. 預設保留 20 km 內的 area，至少 Top 10。
3. 候選不足 10 個時逐步擴至 30 km；仍不足才回傳現有候選。
4. 若 Routes API 可用，可對初選 Top areas 做精確時間校正；不可對全台每個 area 呼叫 Routes。
5. Area ranking 完成後取 Top 10 進入 Places。

### 11.6 Places 餐廳候選

對 Top areas 的 centroid 執行 Nearby Search New，限定餐廳相關 type。每區目標 10 至 20 間，依 place id 去重，總候選目標 50 至 150。

FieldMask 僅要求實際需要欄位，例如 id、displayName、location、rating、userRatingCount、priceLevel、regularOpeningHours、primaryType、formattedAddress；正式環境禁止 `*`。

Google Places 失敗或未設定 key 時，讀取 `data/demo/fallback_restaurants.json`。Fallback 必須是手動建立、公開授權或團隊有權使用的資料，不能把 Google API 完整回應長期落盤冒充本地資料。Place ID 可保存；其他欄位與照片遵守 Google Maps Platform 當下政策。

### 11.7 D 當下情境適配

Hard filter：

- 非餐廳類型
- 缺少座標
- 明確顯示目前未營業

營業資訊缺失時不直接刪除，但降低信心並在 response 標記。

```text
D = 0.60 × TravelTimeFit + 0.40 × RideWorthiness
```

- `TravelTimeFit`: 優先用 Routes；fallback 使用 `Haversine × 1.30`，再用 Train 有效行程的 period median speed 估算。速度不能手動寫死為簡報數字。
- `RideWorthiness`: `<1 km` 很低、1 至 2 km 中低、2 至 10 km 高、10 km 以上依 rider p90 距離逐漸下降。

### 11.8 POI 品質

```text
POIQuality = 0.70 × RatingScore + 0.30 × ReviewConfidence
ReviewConfidence = scale(log(1 + userRatingCount))
```

Rating 缺失時 component unavailable 並重新分配 Q 內權重；不可把缺失當 0 星。第二版可改 Bayesian average，第一版先保留可解釋性。

### 11.9 最終排序

```text
RestaurantScore = 0.60 × AreaScore
                + 0.20 × D
                + 0.20 × POIQuality
```

依分數降序取 Top 5。相同分數依 review confidence、距離、place id 依序穩定排序，確保重跑可重現。

## 12. 離線評估

### 12.1 評估題目

每筆 Validation/Test trip 形成一題：只使用該時間以前可取得的 rider 與群體歷史，輸入 rider、pickup、period、weekday class，預測 destination area。

主要報告：lunch 與 dinner trips。次要報告：所有 periods。actual destination 為 noise 或不在候選半徑內時，分開報告 coverage，不可直接刪掉後只呈現較漂亮的命中率。

### 12.2 必較模型

| 模型 | 說明 |
| --- | --- |
| Global Period Popularity | 只看全體時段熱門區域 |
| Origin-Period Popularity | 同 pickup area、period、weekday class 最常前往的 destination；這是強基準 |
| A only | 完整 area attraction |
| A + C | 加入個人移動習慣 |
| A + B | 加入相似 rider |
| A + B + C | 完整模型 |

### 12.3 指標

- HitRate@5、HitRate@10
- MRR@5
- NDCG@5
- Candidate coverage
- Catalog/area coverage
- 平均推薦距離
- Popularity concentration
- 依 `<3`、`3–9`、`>=10` trips 分群的結果
- lunch、dinner、weekday、weekend 分群結果

主要模型若沒有穩定優於 Origin-Period Popularity，停止宣稱個人化提升；保留最簡單且結果最佳的模型，並記錄失敗假設。

## 13. Serving 資料模型

最低需求：

- `areas(area_id, centroid_lat, centroid_lng, cluster_size, region_label, radius_p90_km, model_version)`
- `area_period_stats(area_id, period, weekday_class, visit_heat, period_lift, cross_area_ratio, source_diversity, return_rate, attraction_score, model_version)`
- `rider_profiles(rider_key, trip_count, p25_distance_km, median_distance_km, p75_distance_km, p90_distance_km, median_duration_min, morning_ratio, lunch_ratio, afternoon_ratio, dinner_ratio, night_ratio, weekend_ratio, cross_area_ratio, fare_midpoint_mean, personalization_level, model_version)`
- `rider_area_stats(rider_key, area_id, period, visit_count, last_visit_at, visit_ratio, model_version)`
- `rider_neighbors(rider_key, neighbor_rider_key, similarity, rank, model_version)`
- `recommendation_requests(request_id, rider_alias, origin_area_id, requested_at, personalization_level, restaurant_source, model_version, latency_ms)`
- `recommendation_items(request_id, rank, place_key, area_id, final_score, score_breakdown_json)`
- `feedback_events(event_id, request_id, place_key, action, occurred_at)`

所有 serving table 要有必要索引與 Alembic migration。`model_version` 由 pipeline run manifest 產生，不可用 `latest` 取代可追溯版本。

## 14. Backend API

### 14.1 Health

```http
GET /health/live
GET /health/ready
```

Ready 應檢查 DB 與必要 artifacts；外部 Places/LLM 不應使服務本身判定死亡。

### 14.2 Demo riders

```http
GET /api/v1/demo/riders
```

只回傳 alias、簡短 persona、trip count、personalization level，不回真實 RiderId。

### 14.3 Recommendation

```http
POST /api/v1/recommendations
```

Request：

```json
{
  "rider_alias": "demo_rider_01",
  "location": {
    "name": "台北車站",
    "latitude": 25.0478,
    "longitude": 121.5170
  },
  "datetime": "2026-09-17T18:30:00+08:00"
}
```

Response 最低欄位：

```json
{
  "request_id": "rec_...",
  "model_version": "...",
  "personalization_level": "full",
  "restaurant_source": "google_places",
  "restaurants": [
    {
      "rank": 1,
      "place_id": "...",
      "name": "範例餐廳",
      "location": {"latitude": 25.05, "longitude": 121.54},
      "rating": 4.6,
      "review_count": 2380,
      "price_level": "PRICE_LEVEL_MODERATE",
      "open_status": "open",
      "source_area_id": "area_...",
      "area_score": 0.86,
      "distance_km": 5.8,
      "estimated_travel_time_min": 18,
      "score": 0.87,
      "score_breakdown": {
        "area_attraction": 0.81,
        "similar_riders": null,
        "personal_mobility": 0.91,
        "context_fit": 0.84,
        "poi_quality": 0.89
      },
      "evidence": [
        {"type": "area_score", "value": 0.86},
        {"type": "travel_estimate_source", "value": "google_routes_matrix"}
      ],
      "explanation": "..."
    }
  ],
  "warnings": [],
  "calculation": {
    "model": "area_a_plus_c",
    "top_areas": [{"rank": 1, "area_id": "area_...", "score": 0.86}],
    "stages": [{"name": "area_ranking", "areas_selected": 10, "duration_ms": 12.3}]
  }
}
```

### 14.4 Rider profile

```http
GET /api/v1/demo/riders/{rider_alias}/profile
```

只供技術 Demo panel 使用。

### 14.5 Ride estimate

```http
POST /api/v1/ride/estimate
```

回傳距離、時間、nullable 的 `encoded_polyline`、明確標記「目前建議路線，不是歷史車輛軌跡」的文字，以及「依歷史資料估算」的金額區間。第一版以 Train 的距離 bin、period、region 的 fare midpoint 分布估 p25 至 p75；樣本不足時退回更粗粒度。不得標成 yoxi 官方報價。

### 14.6 Feedback

```http
POST /api/v1/feedback
```

允許 action：`impression`、`restaurant_clicked`、`explanation_opened`、`ride_clicked`。以 request id 與 place key 去重必要事件。

### 14.7 錯誤格式

所有錯誤使用統一 schema：

```json
{
  "error": {
    "code": "PLACES_UNAVAILABLE",
    "message": "目前無法取得即時餐廳資料，已改用展示資料。",
    "request_id": "...",
    "retryable": true
  }
}
```

## 15. Explanation Service

輸入只允許結構化 evidence，不提供完整行程歷史或真實 RiderId。輸出最多 60 個中文字，不得編造口味、情緒、同行者或餐廳特色。

優先順序：

1. LLM enabled 且成功：生成自然語句。
2. LLM timeout、格式錯誤或未啟用：使用 deterministic template。

Template 範例：

> 這間餐廳位在你晚餐時段常見的移動範圍內；相似移動習慣的乘客也常前往這個區域。

推薦 API 不得因 explanation 失敗而整體失敗。

## 16. Frontend UX

主要 route 維持單一地圖頁，使用 bottom sheet 狀態機：

```text
HOME
LOCATION_SELECTION
RECOMMENDING
RESULTS
RESTAURANT_DETAIL
RIDE_CONFIRMATION
ERROR
```

### 16.1 必要互動

- Home 顯示目前位置與「今天吃什麼」入口。
- 可選三種 Demo persona：full、light、cold。
- Loading 以簡短自然語句說明正在尋找餐廳，不顯示內部計算細節或偽造逐步 AI 思考。
- Results 同時顯示 Top 5 列表與編號 marker。
- 點列表會 focus marker；點 marker 會 focus 對應卡片。
- Detail 顯示可取得的店家資訊、營業狀態、距離、預估時間與簡短推薦理由；示範資料不可冒充真實店家。
- 面向一般使用者的畫面不顯示模型分數、計算階段或內部權重；供審查的計算依據仍保留在 API 回應與測試中。
- 「搭 yoxi 前往」只進入模擬確認畫面，必須明確標示 Demo。
- 外部服務 fallback 時，畫面可顯示不干擾流程的「展示資料」標記。

### 16.2 視覺與可用性

- 可以使用黃、黑、白建立叫車服務視覺，但沒有正式資產時不得使用未授權 logo，也不得讓人誤認為正式 yoxi App。
- 以 390×844 mobile viewport 為主要 Demo 尺寸，同時支援桌面置中預覽。
- 色彩對比、鍵盤 focus、button label、loading/error announcement 必須可用。
- 不引入 Redux；優先使用 React Context 或小型 store。

## 17. Fallback 與可靠性

| 失敗 | 行為 |
| --- | --- |
| Rider 不存在 | Cold Start，A only |
| 3 至 9 筆 | Light personalization，A+C |
| B 無有效 neighbor | 移除 B 並重分配 AreaScore 權重 |
| Top area 無餐廳 | 查下一個 area |
| 餐廳不足 5 間 | 擴大半徑一次，再用合法 fallback 補足 |
| Places timeout/error | fallback restaurants；log source |
| Routes timeout/error | Haversine × 1.30 與歷史 period speed |
| LLM timeout/error | template explanation |
| DB unavailable | Ready false；API 回傳明確 503 |
| Backend error | 前端保留重試與返回首頁，不顯示 stack trace |

外部 API timeout 建議 2.5 秒，最多 retry 一次，只重試 timeout、429、5xx，並加入 jitter。實際值寫入 config。

## 18. 測試規格

### 18.1 Pipeline

- schema、編碼、datetime、fare parser
- 所有 exclusion rule
- period 與 weekday boundary
- Haversine 與弧度換算
- Train-only fit 與 leakage guard
- 同一 input 和 seed 產出相同 artifact hash
- 1,000 列小 fixture 可在 CI 完整跑完

### 18.2 Ranking

- component 範圍皆為 0 至 1
- 缺失 component 正確 reweight
- 未知 rider 只走 A
- 3 至 9 筆不使用 B
- 至少 10 筆才可使用 B
- `<1 km` rideworthiness 低於 2 至 10 km
- 固定輸入的排名 deterministic
- 禁止 Test fit scaler 或 neighbors

### 18.3 Backend

- schema validation
- alias 不洩漏 RiderId
- mocked Places/Routes/LLM success、timeout、429、500
- DB transaction 與 feedback idempotency
- OpenAPI 與 response contract snapshot

### 18.4 Frontend

- 狀態機 transition
- loading、empty、fallback、error
- 列表與 marker 同步
- 一般使用者畫面不露出模型分數與技術用語，示範餐廳和非正式叫車仍有清楚標示
- mobile viewport visual smoke test

### 18.5 E2E 必測場景

1. Full rider → Top 5 → detail → ride confirmation
2. Cold rider → A only → 可完成流程
3. Places fail → fallback → 可完成流程
4. LLM fail → template → 可完成流程
5. Backend 503 → 可理解錯誤與 retry

## 19. CLI 與開發指令

Codex 應提供一致入口，實際可用 Makefile 或 task runner：

```bash
make bootstrap
make data-audit
make cluster-experiments
make preprocess
make evaluate
make load-db
make dev
make test
make e2e
make demo-check
```

`make demo-check` 至少檢查 DB、serving artifacts、fallback data、backend、frontend 與必要環境變數。

## 20. 完成定義

整體專案只有在以下全部成立時才算完成：

- Phase 0 至 8 全部通過或有明確核准的刪減。
- 可從 raw CSV 重建所有 serving artifacts。
- 離線評估無時間洩漏，且公開報告誠實呈現 baseline。
- 新環境依 README 可啟動。
- Full、light、cold 都能完成推薦流程。
- Places、Routes、LLM 任一失敗不會讓 Demo 中斷。
- 五個 E2E 場景通過。
- UI 清楚標示 Demo 與非官方估價。
- Git 不含 raw data、secret、真實 RiderId 對照與不當快取的 Google response。
- 有兩分鐘展示腳本及展示前自動檢查。

## 21. 目前仍待使用者決定的事項

這些不阻擋 Phase 0 至 4：

- 是否已有可用的 Google Maps、Places、Routes key 與計費帳戶
- 是否有正式授權的 yoxi 品牌資產
- Demo 部署位置與公開範圍
- Runtime LLM provider 與模型；若未決定則維持 template 為主
- 是否顯示餐廳照片；第一版預設不顯示，降低成本與快取政策風險

## 22. 官方 API 參考

- [Nearby Search New](https://developers.google.com/maps/documentation/places/web-service/nearby-search)
- [Places API FieldMask](https://developers.google.com/maps/documentation/places/web-service/choose-fields)
- [Places API policies and caching](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Compute Routes](https://developers.google.com/maps/documentation/routes/compute_route_directions)

官方文件目前要求 Places API New 與 Routes 回應指定 FieldMask；Place ID 可長期保存，但其他 Places 資料與照片須遵守其快取和歸屬規則。實作前若政策或計費頁面更新，Codex 應以當下官方文件為準並在 `DECISIONS.md` 記錄。

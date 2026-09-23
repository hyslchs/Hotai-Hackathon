# yoxi AI Demo

這是一個**非官方**的台北移動資料展示系統。它不會知道使用者的口味，也不會真的派車、付款或報出 yoxi 官方價格。它做的是：用匿名且受保護的歷史移動模式，找出某個時段可能值得前往的區域，再用餐廳資料或合成 fallback（備援展示資料）呈現 Top 5。

目前 Taipei Demo 已進入 Phase 9 的「可檢視即時計算」範圍：

- 固定且可重現的 A+C 排序：區域吸引力加上個人移動距離習慣；未驗證有效的相似乘客 B 已停用。
- Demo serving 會依 Persona 加入距離防護：cold 預設 8 km，full/light 依個人中位移動距離限制在 6–10 km；可接受範圍內再加入 20% 近距偏好，避免台北車站直接推薦過遠區域。
- 即時餐廳候選會跨區域輪流取樣，目標每個區域最多兩間；若供應商只回傳單一區域，才填滿必要的 Top 5。
- 完整資料、少量資料、初次使用者三種展示情境。
- Google Places/Routes 的選用式串接；沒有 key、逾時或外部服務失敗時仍以合法合成資料完成展示。
- 每次按下推薦，後端會以既有、Train-only（訓練期）的區域模型先排出最多 10 個區域，再找餐廳、估算最多 20 條前往路線，並回傳可閱讀的計算紀錄。這不是每次重新訓練模型，也不會讀取原始行程。
- 設定受限制的 Google Maps JavaScript 瀏覽器金鑰時，地圖可以點選目前位置、顯示推薦區域與餐廳標記；選餐廳後會畫出目前建議路線。這條線不是歷史車輛軌跡。
- 最多 60 個中文字的固定推薦說明；沒有設定 LLM 時不影響排序或流程。
- 以 Train（訓練期）資料的匿名統計區間估算車資，並明確標示「非 yoxi 官方報價」。
- 模擬叫車確認與可重送、不重複的曝光／點擊事件。

## 先理解資料與隱私界線

原始行程、真實 RiderId（乘客識別碼）、.env 金鑰和外部 Places 完整回應都不能放入 Git。原始資料只留在 data/raw/；模型輸出、清理 Parquet 和展示 artifact 也都在本機產生並被忽略。

因此「乾淨 clone」可以安裝程式，但無法憑空產生資料結果。你需要自行提供原始 CSV，並依下方首次建立步驟產生本機 artifact。兩分鐘展示腳本適用於 artifact 已存在的情況。

## 需要的工具

- Python 3.12
- Node.js 22 或更新版本與 npm
- Docker Desktop
- GNU Make（可選；Windows 可用 Git Bash 或 WSL）

Windows PowerShell 沒有 make 時，請直接執行每個指令旁列出的 PowerShell 等價指令。

## 一次性的首次資料建立

1. 複製 .env.example 為 .env，並設定一個非空的 RIDER_HASH_SALT。不要把 .env 提交。
2. 將授權的原始 CSV 放到 data/raw/yoxi_數據資料.csv。
3. 安裝依賴。

~~~
.\.venv\Scripts\python.exe scripts/bootstrap.py
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -r pipeline/requirements.txt
npm --prefix frontend install
~~~

GNU Make 等價指令是 make bootstrap。

4. 依序建立並驗證資料。Phase 2/3 在完整資料上需要較久，並非兩分鐘展示的一部分。

~~~
.\.venv\Scripts\python.exe scripts/data_audit.py
.\.venv\Scripts\python.exe scripts/preprocess.py
.\.venv\Scripts\python.exe scripts/cluster_experiments.py
.\.venv\Scripts\python.exe scripts/phase3_taipei_demo.py --stage all
.\.venv\Scripts\python.exe scripts/build_ride_estimates.py
~~~

Make 等價指令依序是 make data-audit、make preprocess、make cluster-experiments、make phase3-demo、make build-ride-estimates。

這會在 data/features/phase3_taipei/ 產生 area、特徵、salted profile、鎖定的 offline evaluation 與 Train-only 歷史車資統計。這些檔案不可提交，但 Compose 的 loader 會以唯讀方式使用它們。

## 啟動展示

### 可選：啟用真實地圖、餐廳與路線

不填金鑰也能完成整個 Demo，但餐廳、評分、車程和地圖會清楚標為合成／靜態備援資料。若希望使用真實的 Google 資料，請在本機 `.env` 填入以下三種不同用途的金鑰；不要把 `.env` 提交。

- `VITE_GOOGLE_MAPS_BROWSER_API_KEY`：只給瀏覽器載入地圖。它必須啟用 Maps JavaScript API，並設定 HTTP referrer（網址來源）限制，例如本機 `http://localhost:5173/*`。這個金鑰會出現在瀏覽器，因此不能拿來呼叫 Places 或 Routes。
- `GOOGLE_PLACES_API_KEY`：只由 backend 呼叫 Places API，取得本次請求的餐廳候選。請設 API 限制與伺服器端限制。
- `GOOGLE_ROUTES_API_KEY`：只由 backend 呼叫 Routes API，先估算候選路線，再在選店時取得一條可畫出的建議路線。請設 API 限制與伺服器端限制。

Places 餐廳內容只存在於單次請求的記憶體中；資料庫只保存本次推薦的 place key、名次與分數，沒有保存完整 Google 回應。瀏覽器地圖金鑰、Places 金鑰與 Routes 金鑰的權限和計費必須由專案擁有者在 Google Cloud 管理；本專案不會自動開通或購買服務。

若本機 5432 已被其他 PostgreSQL 使用，先在 .env 設定 POSTGRES_PORT=55432；若要從主機直接執行 load-db 或 benchmark，也要把 DATABASE_URL 內的 localhost port 改成 55432。Compose 容器之間仍使用預設的內部 5432。

~~~
$env:POSTGRES_PORT = "55432" # 僅在 5432 已被占用時設定
docker compose up --build
~~~

Compose 啟動順序是：

1. PostgreSQL 健康檢查。
2. Alembic migration（資料庫結構升級）。
3. Loader 載入本機既有的 aggregate artifact。
4. Backend 與 frontend。

可開啟：

- Frontend：<http://localhost:5173>
- Backend liveness：<http://localhost:8000/health/live>
- Backend readiness：<http://localhost:8000/health/ready>

停止服務但保留本機資料庫：docker compose down。只有明確想刪除本機資料庫時才使用 docker compose down -v。

## 兩分鐘展示腳本

前提：已完成首次資料建立，且 Compose 已啟動。

1. 執行展示前檢查：

~~~
.\.venv\Scripts\python.exe scripts/demo_check.py
~~~

看到 DEMO READY 才開始。它會檢查 .env 的 salt、artifact、fallback 餐廳、backend、資料庫 readiness 與 frontend。

2. 在手機大小視窗（390×844）開啟 frontend，選「完整資料」與「台北車站」，按「今天吃什麼」。
3. 按「查看這次怎麼算」，展示已完成的區域排序、餐廳候選與路線估算紀錄。這是可查核的處理紀錄，不是 LLM 的內部思考。
4. 說明 Top 5 是由已鎖定的區域／移動證據、當次路線與公開店家欄位排序，不是由 LLM 排名。
5. 開一間餐廳，展示「推薦原因」與「歷史車資估算」。有真實地圖時，也展示建議路線；強調價格是 Train 歷史統計、不是官方報價，路線也不是歷史軌跡。
6. 按「搭 yoxi 前往（模擬）」並展示「不會建立真實訂單」。
7. 回到情境選擇，切換「初次使用」：技術面板會把缺少的個人化 component 顯示為「目前不可用」，不假裝有資料。
8. 選「台北東北測試點」或在沒有 Google key 的環境展示 fallback；流程仍完成且畫面會標示展示資料。

## 測試與開發指令

~~~
# 全部 Python pipeline/backend 測試
.\.venv\Scripts\python.exe -m pytest

# 前端單元測試、型別檢查與正式 bundle
npm --prefix frontend run test:run
npm --prefix frontend run build

# 五個手機 Chromium E2E 情境
npm --prefix frontend run e2e -- --workers=1 --reporter=line

# 展示前檢查
.\.venv\Scripts\python.exe scripts/demo_check.py

# Git 安全邊界檢查
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_tracking.ps1
~~~

Make 等價指令：make test、make e2e、make demo-check、make safety-check。若 PowerShell 找不到 make，那是工具未安裝，不是專案測試失敗。

## 已知限制與可宣稱範圍

- 沒有 Google Places/Routes key 時，餐廳、評分與車程是明確標示的合成展示資料。
- 沒有有效的 Maps 瀏覽器金鑰或 Google 載入失敗時，地圖會使用靜態備援；仍可完成推薦流程，但不能把它說成真實互動地圖。
- 沒有 LLM provider 時，系統使用固定模板；LLM 永遠不能決定排名。
- 這份 offline evaluation 只能支持「歷史移動行為可預測特定時段可能前往的區域」，不能支持「系統知道使用者口味」或「一定喜歡某餐廳」。
- 本專案不含正式 yoxi 品牌資產、登入、派車、付款、訂位、公開部署或官方車資。

更多研究限制、模型選擇證據與已接受的決策在 docs/PROJECT_SPEC.md、docs/DECISIONS.md 與 docs/exec-plans/completed/。

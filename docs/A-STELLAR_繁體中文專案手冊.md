# A-STELLAR 繁體中文專案手冊

> Jezero Crater（耶澤羅隕石坑）探索原型。此文件是專案的繁體中文導覽、安裝與操作指南；程式碼、API 欄位、環境變數與原始科學術語維持英文，避免造成不相容。

## 1. 專案用途

A-STELLAR 是一個火星 Jezero 區域探索原型，提供：

- React + TypeScript 地圖介面，使用 NASA Mars Trek 影像圖層。
- FastAPI 後端與版本化 REST API。
- 以 DEM（數值高程模型）為來源、可重現的 A* 地形路徑規劃。
- 選用的 A0 任務協調器，以及 A1、A2、A3、A4、A6 科學／證據工作者。
- 計算式路徑的驗證、溯源中繼資料與持久化儲存。

這是研究與原型系統，**不會認證路徑安全性**。未完成 NASA 地圖、座標與 DEM 對準驗證前，前端會刻意隱藏已計算路徑的地圖幾何線。

## 2. 專案結構

```text
frontend/                 React 使用者介面、NASA 地圖、型別化 API 用戶端
backend/app/api/          FastAPI 路由與錯誤處理
backend/app/contracts/    API、聊天、路徑與工作者資料合約
backend/app/planning/     DEM 網格、A* 搜尋、驗證、路徑儲存
backend/app/coordinator/  A0 協調、政策、聊天與選用模型整合
backend/app/agents/       A1/A2/A3/A4/A6 工作者套件
backend/app/evidence/     證據、地質、觀測與預覽工具
backend/tests/            後端測試
data/                     小型 fixtures、樣本、產生物與本機資料位置
docs/                     英文原始技術文件
scripts/                  Docker、資料取得與驗證腳本
```

## 3. 快速啟動（本機開發）

請以兩個 PowerShell 視窗分別執行後端與前端。

### 3.1 後端

需求：**Python 3.10**。此專案目前釘選的科學套件不支援工作區中的 Python 3.14。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-dev.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

可用網址：

| 用途 | 網址 |
| --- | --- |
| 健康檢查 | `http://127.0.0.1:8000/api/v1/health` |
| 就緒檢查 | `http://127.0.0.1:8000/api/v1/ready` |
| 互動式 API 文件 | `http://127.0.0.1:8000/docs` |
| OpenAPI 規格 | `http://127.0.0.1:8000/openapi.json` |

若要同時安裝地形規劃相依套件，將安裝指令改為：

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints-dev.txt -e ".[dev,planning]"
```

### 3.2 前端

需求：Node.js 22 以上。

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

在瀏覽器開啟 Vite 輸出的網址，通常為 `http://localhost:5173`。開發伺服器會把 `/api/...` 自動代理到 `http://127.0.0.1:8000`，因此不需另外設定 CORS。

若遇到 Vite 舊版最佳化相依檔案錯誤：

```powershell
cd frontend
npm.cmd run dev -- --force
```

然後硬重新整理瀏覽器；必要時在 DevTools 啟用 **Disable cache**。

## 4. 執行模式與設定

複製 `.env.example` 成未追蹤的私有設定檔。**不要提交 API 金鑰或真實資料路徑。**

```dotenv
OPENAI_API_KEY=
A_STELLAR_A0_MODEL=gpt-6.1-sol
A_STELLAR_A0_MODE=agentic
A_STELLAR_ROUTING_MODE=computed
A_STELLAR_DATASET_DIR=/absolute/path/to/dataset
A_STELLAR_PLANNING_PROFILE=/absolute/path/to/A-STELLAR/data/samples/a0-planning-profile.example.json
A_STELLAR_ROUTE_STORE=/absolute/path/to/writable/routes
A_STELLAR_A0_USAGE_STORE=/absolute/path/to/writable/a0-usage
A_STELLAR_A0_MAX_REQUESTS=20
A_STELLAR_A0_BUDGET_USD=2
```

| 設定 | 說明 |
| --- | --- |
| `A_STELLAR_ROUTING_MODE` | `mock`（預設）或 `computed`。前者回傳明確標記的假資料；後者讀取設定的 DEM 並規劃／驗證路徑。 |
| `A_STELLAR_A0_MODE` | `deterministic` 或 `agentic`。Agentic 模式需要 `OPENAI_API_KEY`。 |
| `A_STELLAR_DATASET_DIR` | 大型外部資料集的根目錄，不應複製進 Git repository。 |
| `A_STELLAR_PLANNING_PROFILE` | DEM、ROI、格網與規劃政策設定檔。 |
| `A_STELLAR_ROUTE_STORE` | 已計算路徑、網格與溯源產物的可寫入目錄。 |

設定值的優先序為：程序環境變數高於指定的 runtime env 檔。

### 計算式規劃的 Linux 範例

```bash
cd backend
python -m pip install -e '.[planning]' pytest==9.2.0 httpx==0.28.1
export A_STELLAR_ROUTING_MODE=computed
export A_STELLAR_DATASET_DIR="$HOME/nasa/project/dataset"
export A_STELLAR_PLANNING_PROFILE="$PWD/../data/samples/a0-planning-profile.example.json"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

樣本 profile 僅適用於已檢查的 CTX raster／window；替換 DEM 時必須重新確認 CRS、解析度、單位與遮罩。

## 5. 使用前端規劃路徑

1. 啟動後端與前端。
2. 開啟前端，選擇 **View Jezero area**。
3. 選擇 **Pick Start**，在地圖上設定起點與終點。
4. 提交 **Plan Route**。

計算式模式可先按 **Load in-coverage example endpoints**，使用已知位於 DEM coverage 內的範例端點。`GET /api/v1/regions` 會提供可用範圍與範例請求。地圖點選仍有可見的「座標尚未驗證」警示；範圍涵蓋不代表地點可通行或可連通。

## 6. REST API 概覽

API 前綴：`/api/v1`。

| 方法與端點 | 用途 |
| --- | --- |
| `GET /health` | 程序存活檢查。 |
| `GET /ready` | 設定是否就緒；不會呼叫模型供應商。未就緒時回傳 HTTP 503。 |
| `GET /regions` | Jezero 規劃區域、範圍、解析度與範例請求。 |
| `POST /routes/plan` | 規劃 mock 或 computed 路徑。 |
| `GET /routes/{route_id}` | 讀取已持久化的 computed 路徑與完整 metadata。 |
| `GET /a0/status` | A0 模式、模型、設定狀態、預算與最近供應商錯誤。 |
| `GET /routes/{route_id}/chat` | 取得該路徑的聊天歷程。 |
| `POST /routes/{route_id}/chat` | 對指定路徑送出聊天／修訂請求。 |

### 規劃請求格式

`POST /api/v1/routes/plan`：

```json
{
  "region_id": "jezero",
  "coordinate_system": "MARS_2000_PLANETOCENTRIC_EAST_360_V1",
  "start": { "longitude": 77.45, "latitude": 18.44 },
  "goal": { "longitude": 77.46, "latitude": 18.45 },
  "mode": "safest",
  "waypoints": []
}
```

規則：

- 經度是東經、範圍 `[0, 360)`；緯度是 planetocentric、範圍 `[-90, 90]`。
- `region_id` 目前只接受 `jezero`。
- `mode` 只能是 `shortest` 或 `safest`。
- 最多 16 個有順序的 `waypoints`；相鄰停靠點不可相同。
- `mock` 回應的距離、時間與風險會是 `null`，且必須帶有明確警告；不能視為真實規劃結果。
- `computed` 結果包含距離與溯源資料，但地圖上的幾何顯示仍受座標對準驗證限制。

## 7. 架構與處理流程

```text
React / Vite 前端
        │  相對 /api/v1 請求
        ▼
FastAPI
 ├─ mock：MissionCoordinator → 明確標記的模擬結果
 └─ computed：RouteAgent → PlanningService
                            ├─ DEM 原生格網與衍生遮罩
                            ├─ 有界 8 向 A* 搜尋
                            ├─ 路徑線段與端點獨立驗證
                            └─ 原子式儲存路徑、網格與溯源
```

computed 管線讀取有界的火星 DEM 視窗；coverage、unknown、blocked 遮罩會防止穿越 NoData，unknown cell 一律不可通過。A* 使用實體投影邊長、禁止越過被阻擋的斜角；`safest` 加上已記錄的非負坡度懲罰。搜尋節點數與時間都有上限，並在寫入前獨立檢查每一段路徑與端點連接器。

## 8. A0 與專業工作者

| ID | 名稱／作用 | 目前定位 |
| --- | --- | --- |
| A0 | 任務協調與路徑規劃協調器 | 可用 deterministic terrain pipeline；LangGraph／模型流程為選用實驗。 |
| A1 | 可通行性 | DEM 坡度原型；需進一步驗證格網與遮罩。 |
| A2 | 熱環境 | 日夜影像原型；DN→溫度與門檻未校準。 |
| A3 | 輻射 | 有來源的歷史情境分析，不是 Jezero 未來 EVA 預測。 |
| A4 | 科學地點／地質 | 樣點與模糊感知地質關聯；不產生地形安全分數。 |
| A6 | 漫遊車歷程／觀測 | 經驗證的有限 Navcam 與路線證據。 |

工作者是 Python 套件與 CLI 預覽程式，**不是各自部署的網路微服務**。大型結果保留於 `data/`，API 回應只帶參考資料與溯源資訊。

選用、無快取的 A0 腳本示範：

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.coordinator.cli --request ../data/samples/a0-mission.json --profile ../data/samples/a0-profile.json --provider scripted --script ../data/samples/a0-script.json
```

此為離線決策重播，不是實際模型呼叫，也不應被表述為已驗證的科學或路徑結果。

## 9. 資料管理與科學限制

```text
data/raw/        大型 DEM／thermal 原始輸入（忽略、不提交）
data/cache/      下載的 NASA/PDS/USGS 產品與收據（忽略）
data/processed/  產生的格網、路徑、報告（忽略）
data/fixtures/   小型共用測試資料（追蹤）
data/samples/    小型溯源與情境設定（追蹤）
```

- 大型外部 raster 由 `A_STELLAR_DATASET_DIR` 明確指定；請勿只為符合預設路徑而移動或複製它們。
- 不要提交 GeoTIFF、金鑰、快取產品或產生路徑。
- 合成 fixtures 不是觀測資料。
- checksum 可識別本機檔案內容／版本完整性，但不等於供應商簽章或科學認證。
- 科學產品、座標、CRS、解析度、單位和地圖對準都需產品層級驗證。

## 10. Docker（整合式正式執行）

Docker 映像會建置 React 前端，並由 FastAPI 在同一 origin 提供 UI 與 API。需安裝 Docker Desktop／Engine 與 Compose v2。

```powershell
python scripts/run_docker.py --env-file C:\absolute\path\to\private.env --dataset-dir C:\absolute\path\to\dataset
```

預設開啟 `http://127.0.0.1:8080`。可使用 `--mode deterministic` 執行離線地形規劃、`--port 8081` 更換埠號、`--dry-run` 檢查掛載輸入，或 `--no-build` 重用既有映像。

Docker 模式會把資料集、planning profile 與私有 env 檔以唯讀方式掛載；路徑、聊天、證據與計數器會儲存在 named volume 中。移除該 volume 會刪除這些持久資料，應先備份。

## 11. 驗證與測試

後端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.coordinator.demo
```

前端：

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

前端 build 同時包含 TypeScript 型別檢查。部分 Starlette/httpx deprecation 與前端 bundle-size 警告已知為非致命警告。

## 12. 重要限制與下一步

- 路徑規劃是原型研究工具，不能宣稱安全、可執行或已通過任務核准。
- 已計算路徑的 DEM／投影控制可驗證，但 NASA WMTS 影像與 DEM 的特徵對準尚未完成，因此前端不應將 computed geometry 視覺化為已對準地圖路徑。
- A1/A2 為原型；A3 情境不代表 Jezero 實測或預報；A4/A6 的證據涵蓋度有限。
- 真正的模型供應商請求可能遇到憑證、配額、HTTP 429、模型相容性或逾時問題。這些失敗會保留稽核資訊並退回確定性流程，不代表模型已成功執行。

詳細英文技術依據請參閱 `docs/setup.md`、`docs/architecture.md`、`docs/agents.md`、`docs/datasets.md`、`docs/docker.md` 與 `docs/README.md`。

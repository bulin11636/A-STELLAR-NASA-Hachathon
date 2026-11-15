# Frontend 改善待辦清單（繁中對照）

此文件是 [英文 frontend TODO](FRONTEND_TODO.md) 的繁中討論版。產品介面、狀態文字、錯誤訊息、控制項，以及為這些工作新增的程式碼註解，**都必須維持英文**。

## 不可違反的原則

- 明確維持火星 wire convention：`MARS_2000_PLANETOCENTRIC_EAST_360_V1`。
- 不可在瀏覽器端放入 OpenAI credentials。
- 必須清楚區別 mock、deterministic computed 與 agentic computed 結果。
- 在獨立完成 NASA WMTS／wire／DEM 地圖對準證據前，不可將 computed route geometry 畫在 NASA 底圖上。
- 不可將任何路徑描述為 safe、validated、recommended 或 optimal。
- 保留既有 typed API client、取消請求、stale-response protection 與後端 error envelope 處理。

## P0 — 阻擋 demo 的可靠性與清楚度

### 請求生命週期與可復原失敗

- [ ] 整合 computed plan request status endpoint：`GET /api/v1/routes/requests/{request_id}`。
- [ ] 整合 chat attempt status endpoint：`GET /api/v1/routes/{route_id}/chat/attempts/{request_id}`。
- [ ] 在 UI 顯示 `running`、`succeeded`、`failed`、`unknown` 狀態。
- [ ] 顯示是否可 retry 與 `retry_after_seconds`；禁止自動重試 model calls。
- [ ] 對 computed planning request 傳送 `Idempotency-Key`，並在結果未確定前保留該 key。
- [ ] 後續 plan 或 chat 失敗時，保留最後一次成功的 route。
- [ ] 新增 replay、conflict、eligible retry 與 unknown outcome 的測試。

### Runtime 狀態與模式揭露

- [ ] 讓 routing mode 明顯可見：`mock`、`computed / deterministic` 或 `computed / agentic`。
- [ ] 顯示 DEM、route store 與 model credentials 是否 ready。
- [ ] 將「設定了 model」與「provider 已接受／可使用」明確區分。
- [ ] 僅在 backend 回傳時顯示 request count 與 estimated/reserved cost。
- [ ] 為 API 無法連線、dataset 缺失、planning profile 無效、credentials 缺失、provider rejection 提供可執行的英文錯誤訊息。

### 文字與編碼品質

- [ ] 修正 `Â·`、`â€”`、`â€¦` 等 mojibake 字元，改為有效 UTF-8 punctuation 或 plain ASCII。
- [ ] 所有新增或修改的 frontend string 必須為英文。
- [ ] 統一 planner、map、A0 status 與 chat panel 的狀態用語。

## P1 — 規劃與證據使用體驗

### 引導式規劃流程

- [ ] 提供清楚順序：選 Jezero 視圖、選起點終點、可選 ordered waypoints、選 objective、送出規劃。
- [ ] computed mode 優先顯示 backend 提供的 in-coverage DEM example。
- [ ] 說明任意 map click 可能在 planning coverage 外，但不可暗示 basemap 已與 DEM 對準。
- [ ] 只保留一個明確的主要操作按鈕；disabled 時需說明原因。

### Route 結果資訊分層

- [ ] 使用精簡 summary 呈現 source、mode、distance、warnings 與下一步。
- [ ] 將詳細 provenance、grid policy、worker status、validation data 放入可展開區塊。
- [ ] mock metrics 必須維持 null，並清楚標示 mock routes 並未通過安全驗證。
- [ ] 顯示 computed rationale、limitations、evidence IDs 與未評估的 specialist inputs。
- [ ] 保留 POST 結果與 stored-route retrieval 間的 metadata consistency checks。

### A0 對話

- [ ] 新增英文 quick prompts：route explanation、`shortest`、`safest`、coordinate-based waypoint edits。
- [ ] 回傳 route revision 時，切換畫面前先摘要其變更。
- [ ] 顯示 route ID、parent relationship、可用時的 cost/usage，並清楚表示資訊性回答未改變路徑。
- [ ] 對 free-form avoidance polygons、arbitrary policy changes、未實作 itinerary optimization 明確標為不支援。

### 地圖與 evidence 處理

- [ ] 區分 NASA imagery/tile failure 與 API failure。
- [ ] 在 map registration 驗證前，維持 computed-geometry display guard。
- [ ] 對 evidence layers 顯示 coverage、provenance、uncertainty、unavailable state 與 source links；不可在前端捏造 hazard 或 temperature map。

## P2 — 細節、無障礙與發布信心

- [ ] 改善窄螢幕與長 route metadata 的 responsive layout。
- [ ] 檢查 keyboard navigation、focus order、labels、`aria-live` 更新與 color contrast。
- [ ] 建立使用 fixtures 的一鍵 demo reset；不可將其假裝為科學資料。
- [ ] 新增 Playwright 流程：mock success、computed success、offline API、missing credentials、invalid metadata、request recovery、Vite proxy failure。
- [ ] 新增 map fitting 與 nearby-stop usability 的 browser acceptance checks。
- [ ] 提供給 judges 與 contributors 的短版英文 demo script。

## 建議交付順序

1. P0 request lifecycle、runtime state 與 text/encoding fixes。
2. P1 guided planning 與 route result hierarchy。
3. P1 A0 conversation 與 evidence presentation。
4. P2 responsive、accessibility 與 browser acceptance coverage。

## 明確不在此 backlog 的範圍

- Browser-side DEM processing、A* search、science fusion 或 direct LLM calls。
- 在 map registration 完成前，將 computed route 畫在 NASA basemap。
- 將 A2 visual mosaics、A3 historical scenarios、A4 geology、A6 rover history 當成自動化 astronaut-safety assessment。

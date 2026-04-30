# everywifi
開發公用 WiFi 熱點 + LoRa IoT 網路

## 系統設計

### 計費模型：後付計量（Pay-as-you-go）

- **Account（帳戶）**：使用者的計費帳戶，設定 `credit_limit`（預算上限，單位：毫元 milli-TWD，1000 = 1 元）和 `balance_used`（已累計費用）。啟用 `billing_enabled` 後才允許上網。
- **RateCard（費率表）**：定義每 MB 費用（毫元）。不同業者可使用不同費率。
- **Session（連線會話）**：每個裝置（依 `device_id` / MAC）連線時建立一個 Session，結束時關閉。多裝置可同時建立 Session，費用共用同一個帳戶的預算上限。
- 每次 OpenWrt 回報流量時即時扣費，當 `balance_used ≥ credit_limit` 時停止服務。

### 區塊鏈帳本（Hash Chain）

每筆 Usage 記錄包含：
- `prev_hash`：前一筆記錄的 `record_hash`（創世記錄為 64 個 `0`）。
- `record_hash`：`sha256(id:user_id:session_id:bytes_used:cost_millitwd:recorded_at:prev_hash)`。

此 Hash Chain 使帳本 append-only 且可稽核，任何事後竄改都可被偵測。

### 跨業者分潤

- **Provider（業者）** + **Node（熱點節點）**：每個 Session 記錄使用的 `node_id`，方便後續按比例結算。

---

## 專案結構

```
everywifi/
├── ledger/                  # 帳本後端 API（Flask + SQLite）
│   ├── app.py               # Flask 應用程式入口
│   ├── database.py          # SQLAlchemy db 物件
│   ├── models.py            # 資料模型
│   │                        #   User, Account, RateCard,
│   │                        #   Provider, Node, Session, Usage
│   └── routes/              # API 路由
│       ├── users.py         # 使用者管理
│       ├── accounts.py      # 帳戶管理（credit_limit, billing_enabled）
│       ├── rate_cards.py    # 費率表管理
│       ├── providers.py     # 業者與節點管理
│       ├── sessions.py      # 裝置連線會話管理
│       ├── usage.py         # 流量扣費（含 Hash Chain 寫入）
│       └── auth.py          # OpenWrt 認證端點
├── openwrt/                 # OpenWrt 整合腳本與設定
│   ├── everywifi-auth.sh    # 登入並驗證使用者
│   ├── everywifi-usage.sh   # 定期回報流量
│   ├── binauth.sh           # nodogsplash BinAuth hook
│   └── nodogsplash.conf     # nodogsplash 設定範例
├── tests/                   # pytest 測試（57 個）
├── requirements.txt
└── README.md
```

## 快速開始

```bash
pip install -r requirements.txt
python3 -m ledger.app          # 啟動帳本 API（http://0.0.0.0:5000）
```

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/users` | 建立使用者 |
| GET  | `/users/<id>` | 查詢使用者 |
| POST | `/users/login` | 登入，取得 token |
| POST | `/accounts` | 建立計費帳戶（`credit_limit` milli-TWD, `billing_enabled`）|
| GET  | `/accounts/<id>` | 查詢帳戶 |
| GET  | `/accounts/user/<user_id>` | 依使用者查詢帳戶 |
| POST | `/accounts/<id>/enable` | 啟用計費 |
| POST | `/accounts/<id>/disable` | 停用計費 |
| PATCH| `/accounts/<id>/credit-limit` | 更新預算上限 |
| GET  | `/rate-cards` | 列出費率表 |
| POST | `/rate-cards` | 建立費率表（`price_per_mb` milli-TWD/MB）|
| GET  | `/rate-cards/<id>` | 查詢費率表 |
| GET  | `/providers` | 列出業者 |
| POST | `/providers` | 建立業者 |
| GET  | `/providers/<id>` | 查詢業者 |
| GET  | `/providers/<id>/nodes` | 列出業者節點 |
| POST | `/providers/<id>/nodes` | 建立節點 |
| POST | `/sessions` | 開始裝置連線會話（`token`, `device_id`, `node_id`）|
| POST | `/sessions/<id>/end` | 結束連線會話 |
| GET  | `/sessions/<id>` | 查詢單一會話 |
| GET  | `/sessions/account/<id>` | 列出帳戶所有會話 |
| GET  | `/sessions/account/<id>/active` | 列出帳戶進行中的會話 |
| GET  | `/usage/user/<id>` | 查詢使用者帳戶狀態 |
| POST | `/usage/deduct` | 扣除流量並計費（OpenWrt 呼叫；寫入 Hash Chain）|
| POST | `/auth` | 驗證是否可上網（OpenWrt 呼叫）|

## 執行測試

```bash
python3 -m pytest tests/ -v
```


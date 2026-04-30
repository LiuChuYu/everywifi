# everywifi
開發公用 WiFi 熱點 + LoRa IoT 網路

## 專案結構

```
everywifi/
├── ledger/          # 帳本後端 API（Flask + SQLite）
│   ├── app.py       # Flask 應用程式入口
│   ├── database.py  # SQLAlchemy db 物件
│   ├── models.py    # 資料模型（User, Plan, Purchase, Usage）
│   └── routes/      # API 路由
│       ├── users.py      # 使用者管理
│       ├── plans.py      # 套餐管理
│       ├── purchases.py  # 購買紀錄
│       ├── usage.py      # 流量查詢與扣除
│       └── auth.py       # OpenWrt 認證端點
├── openwrt/         # OpenWrt 整合腳本與設定
│   ├── everywifi-auth.sh   # 登入並驗證使用者
│   ├── everywifi-usage.sh  # 定期回報流量
│   ├── binauth.sh          # nodogsplash BinAuth hook
│   └── nodogsplash.conf    # nodogsplash 設定範例
├── tests/           # pytest 測試
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
| GET  | `/plans` | 列出套餐 |
| POST | `/plans` | 建立套餐 |
| POST | `/purchases` | 新增購買紀錄 |
| POST | `/purchases/<id>/pay` | 確認付款，啟動套餐 |
| GET  | `/purchases/user/<id>` | 查詢使用者購買紀錄 |
| GET  | `/usage/user/<id>` | 查詢使用者用量 |
| POST | `/usage/deduct` | 扣除流量（OpenWrt 呼叫） |
| POST | `/auth` | 驗證是否可上網（OpenWrt 呼叫） |

## 執行測試

```bash
python3 -m pytest tests/ -v
```

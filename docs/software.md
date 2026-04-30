# 軟體架構說明 Software Architecture

## 1. 技術棧 Tech Stack

| 層次 | 技術 |
|------|------|
| 作業系統 | OpenWRT 23.05 (Linux 5.15) |
| 語言 | Python 3.10+ |
| 網路 | nftables, tc (iproute2), hostapd, dnsmasq |
| VPN | WireGuard |
| 帳本儲存 | SQLite 3 (本地帳本快取) |
| P2P | UDP Gossip over WireGuard |
| LoRa 驅動 | pyserial (USB) / spidev (SPI) |
| API | 輕量 HTTP REST (Python http.server) |

---

## 2. 模組說明

### 2.1 `src/main.py` — 協調器 Orchestrator

- 啟動所有子模組
- 處理跨模組事件（LoRa 確認 → Ledger 獎勵 → WiFi 解鎖）
- 提供 `/api/status` 端點供監控使用

### 2.2 `src/ledger/` — 代幣帳本

#### `ledger.py`
- `Account` 類別：管理帳戶鏈（BlockLattice）
- `Block` 類別：`send` / `receive` / `open` / `change` 區塊
- `Ledger` 類別：本地帳本管理，SQLite 儲存
- PoW 計算：Blake2b hash puzzle

#### `nano_rpc.py`
- 若需接入真實 Nano 網路的 RPC 客戶端
- 支援 `account_info`, `send`, `receive_pending`

### 2.3 `src/wifi/` — WiFi 管理

#### `captive_portal.py`
- 輕量 HTTP server (asyncio)
- 處理認證、代幣支付確認
- 重定向未認證設備

#### `bandwidth.py`
- 呼叫 `tc` 指令管理 HTB qdisc
- `set_rate(mac, rate_kbps)` 依 MAC 調整速率
- 免費層: 1024 Kbps；付費層: 動態

#### `auth.py`
- MAC 白名單管理（nftables set）
- 會話管理：計時、流量配額追蹤

### 2.4 `src/lora/` — LoRa 閘道

#### `lora_gateway.py`
- 與 LoRa 模組通訊（USB serial / SPI）
- 解析 LoRaWAN 封包
- 廣播位置聲明包

#### `location.py`
- RSSI 三角定位計算
- 多節點位置確認
- 產生位置驗證事件

### 2.5 `src/vpn/` — WireGuard 管理

#### `wireguard.py`
- 生成 WireGuard keypair
- 管理 peer 配置（`/etc/wireguard/wg0.conf`）
- 動態加入/移除 peer

### 2.6 `src/p2p/` — 分散式 Gossip

#### `gossip.py`
- UDP 廣播/單播 gossip 協議
- 傳遞：帳本區塊、位置確認、peer 清單
- 防重播：消息 ID + TTL

---

## 3. API 端點

| 路徑 | 方法 | 說明 |
|------|------|------|
| `/api/status` | GET | 節點狀態（帳本高度、peer 數、LoRa 狀態）|
| `/api/account/{addr}` | GET | 帳戶餘額與帳戶鏈 |
| `/api/pay` | POST | 提交支付請求（JSON: address, amount）|
| `/api/wifi/clients` | GET | 目前連線用戶清單 |
| `/api/lora/peers` | GET | LoRa 範圍內節點清單 |

---

## 4. 設定檔 Configuration

所有設定集中在 `src/config.py`（或環境變數）：

```python
# 帳本
LEDGER_DB_PATH = "/opt/everywifi/data/ledger.db"
REWARD_PER_LOCATION = 10_000_000_000_000_000_000_000_000  # 10 EWF (raw)
TRAFFIC_RATE_PER_EWF = 10 * 1024 * 1024  # 10 MB per 1 EWF

# WiFi
FREE_RATE_KBPS = 1024       # 1 Mbps free tier
DEFAULT_PAID_RATE_KBPS = 10240  # 10 Mbps paid tier
WIFI_IFACE = "wlan0"
LAN_IFACE = "br-lan"

# LoRa
LORA_DEVICE = "/dev/ttyUSB0"  # or "/dev/spidev0.0"
LORA_FREQ_MHZ = 868.1          # 868 MHz EU / 915 MHz US
MIN_CONFIRMATIONS = 3           # 位置確認所需節點數

# P2P
P2P_PORT = 7777
BOOTSTRAP_PEERS = ["10.0.0.1:7777"]  # WireGuard VPN IPs
GOSSIP_INTERVAL = 10  # seconds
GOSSIP_FANOUT = 3

# VPN
WG_IFACE = "wg0"
WG_PORT = 51820
WG_SUBNET = "10.99.0.0/24"
```

---

## 5. 部署流程 Deployment

```
1. 燒錄 OpenWRT 韌體（見 docs/firmware.md）
2. SSH 登入：ssh root@192.168.1.1
3. 執行安裝腳本：
   opkg update && opkg install python3 python3-pip
   pip3 install pyserial aiohttp
4. 複製本專案至 /opt/everywifi
5. 設定 /opt/everywifi/src/config.py
6. 設定 WireGuard（scripts/setup_vpn.sh）
7. 啟動服務：
   /etc/init.d/everywifi enable
   /etc/init.d/everywifi start
```

---

## 6. Init Script

`/etc/init.d/everywifi`:
```sh
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=95
STOP=01

start_service() {
    procd_open_instance
    procd_set_param command python3 /opt/everywifi/src/main.py
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
```

---

## 7. 監控 Monitoring

```bash
# 查看節點狀態
curl http://127.0.0.1:8080/api/status

# 查看帳本
curl http://127.0.0.1:8080/api/account/<your_address>

# 查看 WiFi 用戶
curl http://127.0.0.1:8080/api/wifi/clients

# 查看 LoRa peers
curl http://127.0.0.1:8080/api/lora/peers

# 查看服務日誌
logread | grep everywifi
```

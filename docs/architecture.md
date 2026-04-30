# EveryWifi 系統架構 System Architecture

## 1. 總覽 Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         EveryWifi Node                          │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │   WAN    │   │  WiFi (AP)   │   │   LoRa Module          │  │
│  │ (ETH 0)  │   │ 2.4G / 5G    │   │  (SX1276 / SX1302)     │  │
│  └────┬─────┘   └──────┬───────┘   └──────────┬─────────────┘  │
│       │                │                       │                 │
│  ┌────▼────────────────▼───────────────────────▼─────────────┐  │
│  │                  OpenWRT Kernel (MT7621)                   │  │
│  │     nftables routing │ br-lan │ tc (HTB shaping)          │  │
│  └────────────────────────┬──────────────────────────────────┘  │
│                           │ Python 3 userspace                  │
│  ┌────────────────────────▼──────────────────────────────────┐  │
│  │                    main.py (Orchestrator)                  │  │
│  │  ┌──────────┐ ┌─────────┐ ┌───────────┐ ┌────────────┐   │  │
│  │  │ WiFi Mgr │ │  LoRa   │ │  Ledger   │ │  VPN/P2P   │   │  │
│  │  │(captive  │ │Gateway  │ │(Nano DAG) │ │(WireGuard) │   │  │
│  │  │ portal)  │ │+Locator │ │           │ │  + gossip  │   │  │
│  │  └──────────┘ └─────────┘ └───────────┘ └────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 元件說明 Component Descriptions

### 2.1 ETH 路由層 (ETH Routing Layer)

- **WAN**: DHCP client / PPPoE on eth0
- **LAN**: Bridge `br-lan` (eth1 + WiFi AP)
- **防火牆**: nftables FORWARD 規則、NAT masquerade
- **流量整形**: `tc` HTB (Hierarchical Token Bucket) 依 MAC 限速
  - 免費用戶: 下行 1 Mbps / 上行 512 Kbps
  - 付費用戶: 動態解鎖至 WAN 線路上限

### 2.2 WiFi 熱點 (WiFi Hotspot)

- OpenWRT `hostapd` 管理 AP
- **Captive Portal**: 輕量 HTTP server (port 80/443) 攔截未認證流量
- 認證流程:
  1. 使用者連接 SSID → DHCP 取得 IP
  2. 任意 HTTP 請求被重定向至 Portal 頁面
  3. 使用者選擇「免費 1Mbps」或「付費高速」
  4. 免費: MAC 加入白名單，套用 1 Mbps HTB class
  5. 付費: 掃描代幣 QR code 或輸入地址完成鏈上支付 → 動態提升 class

### 2.3 LoRa WAN 閘道 + 位置驗證

- **硬體介面**: SPI / USB 連接 LoRa 模組
- **封包格式**: LoRaWAN Class A 上行包含裝置 DevEUI + GPS 座標（若有）/ RSSI 訊號強度
- **位置計算**:
  - 多節點 RSSI 三角定位
  - 若節點配備 GPS，則直接使用 GPS 座標
- **位置驗證流程**:
  1. 新節點廣播位置聲明包
  2. 至少 3 個鄰近節點接收並確認 RSSI 合理性
  3. 共識後，節點帳戶獲得位置獎勵代幣
- **防女巫攻擊**: 代幣獎勵基於 LoRa 實體訊號強度，偽造虛假位置需要實體硬體

### 2.4 代幣帳本 (Token Ledger)

採用 **Nano Block-Lattice** 架構：

- 每個帳戶擁有獨立的區塊鏈（帳戶鏈）
- 交易分為 `send` 和 `receive` 兩種區塊
- 共識: **dPoS** (delegated Proof-of-Stake) — 節點間 P2P 投票
- 工作量證明 (PoW): 防垃圾交易，輕量 Blake2b PoW
- **代幣單位**: `EWF` (EveryWifi)
  - 位置獎勵: 每次驗證 +10 EWF
  - 流量計費: 1 EWF = 10 MB 高速流量

### 2.5 VPN (WireGuard)

- 節點間透過 WireGuard 建立加密隧道
- 拓撲: Hub-and-Spoke（Bootstrap node 作為 Hub）或 Full Mesh
- 用途:
  - 帳本 P2P 訊息傳遞
  - 管理平面（SSH / API）加密
  - 選擇性: 使用者付費流量走 VPN 出口

### 2.6 分散式 P2P Gossip

- 節點定期廣播自身狀態（帳本高度、鄰居清單、LoRa 接收到的位置）
- 使用 UDP gossip 協議（fanout=3，週期 10s）
- 新節點透過 Bootstrap list 加入網路

## 3. 資料流 Data Flows

### 3.1 使用者付費高速流量

```
User Device → WiFi AP → Captive Portal
    → 顯示 QR code (帳戶地址 + 金額)
    → 使用者錢包發送 EWF
    → Ledger 確認交易
    → WiFi Mgr 呼叫 tc 提升 HTB class
    → 使用者享有高速流量
```

### 3.2 LoRa 位置驗證與獎勵

```
Node A 廣播位置包
    → Node B, C, D 收到，測量 RSSI
    → B, C, D 簽署確認包，P2P 廣播
    → 收到 ≥3 確認 → Ledger 建立 send 區塊 (系統 → Node A)
    → Node A 建立 receive 區塊
    → 帳本更新完成
```

## 4. 安全考量 Security

| 威脅 | 緩解措施 |
|------|---------|
| 偽造位置 | LoRa 實體 RSSI 驗證 + 多節點共識 |
| 雙花攻擊 | Block-Lattice 帳戶鏈 + PoW |
| 女巫攻擊 | 每個 LoRa DevEUI 唯一，需要實體硬體 |
| WiFi 旁路 | nftables FORWARD 嚴格白名單 |
| 管理存取 | WireGuard VPN + SSH key-only |
| 流量竊聽 | WireGuard 加密隧道 |

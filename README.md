# EveryWifi

**OpenWRT-based distributed public WiFi + LoRa IoT network**

EveryWifi 是一個基於 OpenWRT 的開源分散式公用 WiFi 及 LoRa IoT 網路平台，搭載 MT7621 晶片，結合 WiFi 熱點與 LoRa 無線技術，透過代幣經濟模型激勵節點部署，並提供免費基礎網路存取。

---

## 特性 Features

| 功能 | 說明 |
|------|------|
| WiFi 熱點 | 提供 1 Mbps 免費基礎連線；付費代幣可解鎖高速流量 |
| LoRa WAN | 裝置間透過 LoRa 驗證實體位置，產生位置信標並獎勵代幣 |
| 代幣帳本 | 基於 Nano Block-Lattice 的輕量級分散式帳本 |
| ETH 路由 | 有線 WAN/LAN 路由（OpenWRT nftables） |
| VPN | WireGuard 節點間加密通道 |
| 分散式 | 節點間 P2P gossip 協議同步帳本與位置資訊 |
| 物理位置 | LoRa RSSI/TDOA 多點定位 |

---

## 快速開始 Quick Start

```bash
# 1. 複製倉庫
git clone https://github.com/LiuChuYu/everywifi.git
cd everywifi

# 2. 閱讀硬體需求
cat docs/hardware.md

# 3. 編譯韌體
bash scripts/build_firmware.sh

# 4. 燒錄後登入 OpenWRT，安裝本套件
bash scripts/install.sh

# 5. 啟動服務
python3 /opt/everywifi/src/main.py
```

---

## 文件 Documentation

- [架構設計](docs/architecture.md)
- [硬體與韌體](docs/hardware.md)
- [韌體編譯與燒錄](docs/firmware.md)
- [軟體架構](docs/software.md)

---

## 目錄結構 Directory Layout

```
everywifi/
├── docs/               # 技術文件
├── firmware/           # OpenWRT 設定檔與編譯腳本
│   ├── config/         # UCI 設定檔 (network, wireless, firewall, dhcp)
│   └── patches/        # 核心 / 套件 patches
├── src/                # 應用程式原始碼 (Python 3)
│   ├── ledger/         # Nano-inspired 代幣帳本
│   ├── wifi/           # 熱點管理 + Captive Portal
│   ├── lora/           # LoRa WAN 閘道 + 位置驗證
│   ├── vpn/            # WireGuard 管理
│   ├── p2p/            # 分散式 gossip 協議
│   └── main.py
├── scripts/            # 安裝 / 建置腳本
└── tests/              # 單元測試
```

---

## 授權 License

MIT License

# 硬體規格與接線 Hardware Specifications & Wiring

## 1. 推薦硬體平台

### 1.1 主板 (Main Board)

| 規格 | 說明 |
|------|------|
| SoC | MediaTek MT7621A (880 MHz dual-core MIPS) |
| RAM | 256 MB DDR3（建議 512 MB） |
| Flash | 32 MB NOR / 128 MB NAND（建議）|
| ETH | 5-port Gigabit switch (MT7530 integrated) |
| WiFi | MT7603 (2.4 GHz) + MT7612 (5 GHz) |
| USB | USB 3.0 × 1，USB 2.0 × 1 |
| UART | 3.3V TTL (115200 8N1) |
| GPIO | 多個可用 GPIO |

**參考硬體**：
- GL.iNet GL-MT1300 (Beryl)
- Xiaomi Mi Router 3G / 4A Gigabit
- Netgear R6220
- 客製 MT7621 開發板（推薦：搭配 M.2 擴充槽）

### 1.2 LoRa 模組

| 方案 | 晶片 | 介面 | 備註 |
|------|------|------|------|
| 推薦: RAK2247 | SX1301 | SPI / USB | mPCIe 介面，官方 OpenWRT 支援 |
| RAK5146 | SX1303 | USB | 最新版，更高靈敏度 |
| WaveShare SX1262 | SX1262 | SPI | 單通道，適合 PoC |
| Dragino PG1301 | SX1301 | USB | |

**建議**: RAK2247 (mPCIe) + MT7621 開發板（含 mPCIe 插槽）

### 1.3 選配 GPS 模組

| 型號 | 介面 | 精度 |
|------|------|------|
| u-blox NEO-M8N | UART / USB | 2.5 m CEP |
| Quectel L76K | UART | 2.5 m CEP |

---

## 2. 接線圖 Wiring Diagram

### 2.1 SPI LoRa 模組接線（以 SX1276 為例）

```
MT7621 GPIO         SX1276
─────────────────────────────
GPIO 6  (SPI CLK)  → SCK
GPIO 5  (SPI MOSI) → MOSI
GPIO 4  (SPI MISO) → MISO
GPIO 3  (SPI CS0)  → NSS
GPIO 2             → RESET
GPIO 1             → DIO0 (IRQ)
3.3V               → VCC
GND                → GND
```

> ⚠️ 確認目標開發板 SPI 腳位與 GPIO 編號，不同板卡可能不同

### 2.2 USB LoRa 閘道（RAK2247 mPCIe）

- 插入 mPCIe 插槽即可，透過 USB 連接 SoC
- 韌體自動識別為 `/dev/ttyUSB0` 或 `/dev/spidev0.0`

### 2.3 GPS UART 接線

```
MT7621 UART1 (GPIO 45/46)    GPS Module
─────────────────────────────────────────
UART1 TX (GPIO 45)  → GPS RX
UART1 RX (GPIO 46)  → GPS TX
3.3V                → VCC
GND                 → GND
```

---

## 3. 天線需求

| 模組 | 天線類型 | 建議增益 |
|------|---------|---------|
| WiFi 2.4G | Dual-band MIMO | 5 dBi |
| WiFi 5G | Dual-band MIMO | 5 dBi |
| LoRa 868/915 MHz | Omnidirectional fiberglass | 3–5 dBi |
| GPS | Patch or active GPS antenna | N/A |

---

## 4. 電源需求

| 元件 | 電流 |
|------|------|
| MT7621 SoC + WiFi | ~600 mA @ 12V (7.2W) |
| RAK2247 LoRa | ~400 mA @ 3.3V (1.3W) |
| GPS | ~25 mA @ 3.3V |
| 合計建議 | 12V 2A (24W) 電源供應器 |

---

## 5. 儲存擴充

- 建議使用 USB 3.0 隨身碟或 microSD（透過 USB 讀卡機）掛載 `/overlay` 或 `/opt`
- 用於儲存帳本資料（可能隨時間增長）
- 建議最小 8 GB，建議 32 GB

---

## 6. DIP 開關 / JTAG

如需 JTAG 除錯：

```
JTAG Pin    MT7621 GPIO
─────────────────────────
TCK         GPIO 17
TMS         GPIO 18
TDI         GPIO 19
TDO         GPIO 20
TRST        GPIO 21
GND         GND
```

---

## 7. 軟體相關 GPIO 設定（DTS overlay）

在 OpenWRT 設備樹中啟用 SPI LoRa：

```dts
&spi0 {
    status = "okay";
    sx127x@0 {
        compatible = "semtech,sx1276";
        reg = <0>;
        spi-max-frequency = <10000000>;
        reset-gpios = <&gpio 2 GPIO_ACTIVE_LOW>;
        dio-gpios = <&gpio 1 GPIO_ACTIVE_HIGH>;
    };
};
```


# 韌體編譯與燒錄指南 Firmware Build & Flash Guide

## 1. 開發環境需求

```bash
# Ubuntu 20.04 / 22.04 LTS 推薦
sudo apt-get update
sudo apt-get install -y \
    build-essential clang flex bison g++ gawk \
    gcc-multilib g++-multilib gettext git libncurses-dev \
    libssl-dev python3-distutils rsync unzip zlib1g-dev \
    file wget curl
```

---

## 2. 取得 OpenWRT 原始碼

```bash
git clone https://git.openwrt.org/openwrt/openwrt.git
cd openwrt
# 使用穩定版本（例如 OpenWrt 23.05）
git checkout v23.05.3
```

---

## 3. 更新套件 Feeds

```bash
./scripts/feeds update -a
./scripts/feeds install -a
```

---

## 4. 套入 EveryWifi 設定

```bash
# 從本倉庫複製設定
cp /path/to/everywifi/firmware/config/openwrt_config .config

# 或手動設定
make menuconfig
```

### 4.1 必要選項（menuconfig）

```
Target System  → MediaTek Ralink MIPS
Subtarget      → MT7621 based boards
Target Profile → [選擇您的硬體，例如 GL-MT1300]

Kernel modules → SPI support → kmod-spi-dev
Kernel modules → USB support  → kmod-usb-serial
                               → kmod-usb-serial-ftdi

Network → WireGuard → wireguard-tools
Network → iptables → kmod-nft-core, nftables
Network → Traffic Control → tc, kmod-sched-core, kmod-sched-htb

Languages → Python3 → python3
                    → python3-pip
                    → python3-asyncio
                    → python3-cryptography
                    → python3-pyserial

Utilities → GPS → gpsd

[選配] Network → LoRa → lora-gateway (if available in feeds)
```

### 4.2 使用預設 .config

```bash
# 複製本專案提供的 .config 範本
cp /path/to/everywifi/firmware/config/openwrt_config \
   /path/to/openwrt/.config
make defconfig
```

---

## 5. 編譯韌體

```bash
# 第一次編譯（含工具鏈，約 1–3 小時）
make -j$(nproc)

# 後續增量編譯
make -j$(nproc) package/feeds/everywifi/compile
```

編譯完成後，韌體位於：
```
bin/targets/ramips/mt7621/
└── openwrt-ramips-mt7621-<board>-squashfs-sysupgrade.bin
```

---

## 6. 燒錄韌體 Flashing

### 6.1 透過 Web UI（LuCI）

1. 登入原廠或現有 OpenWRT Web 介面
2. System → Backup/Flash Firmware
3. 上傳 `.bin` 檔案
4. 取消勾選「Keep settings」（首次安裝時）
5. 點擊 Flash

### 6.2 透過 TFTP（原廠韌體救磚）

```bash
# 將電腦 IP 設為 192.168.1.2/24
# 啟動路由器時按住 Reset 按鈕進入 TFTP 模式

# Linux
sudo apt-get install tftpd-hpa
cp openwrt-*.bin /var/lib/tftpboot/firmware.bin
# 路由器 TFTP client 會自動下載並燒錄

# macOS
# 使用 tftp 指令
tftp
> connect 192.168.1.1
> binary
> put openwrt-*.bin
```

### 6.3 透過 UART + U-Boot

```bash
# 連接 UART (115200 8N1)
screen /dev/ttyUSB0 115200
# 或
minicom -D /dev/ttyUSB0 -b 115200

# 開機時按任意鍵進入 U-Boot
# U-Boot 命令列:
setenv ipaddr 192.168.1.1
setenv serverip 192.168.1.2
tftp 0x80010000 firmware.bin
erase 0xbc050000 +0xfb0000
cp.b 0x80010000 0xbc050000 ${filesize}
boot
```

---

## 7. 首次開機設定

```bash
# SSH 連入（預設 IP: 192.168.1.1）
ssh root@192.168.1.1

# 設定密碼
passwd

# 安裝 EveryWifi 套件
opkg update
bash /tmp/install.sh   # 從 USB 或網路複製 install.sh
```

---

## 8. LoRa 套件安裝（非內建於韌體時）

```bash
# 安裝 lora-gateway 套件（需要對應 feeds）
opkg install kmod-spi-dev python3 python3-pyserial

# 對於 RAK2247 USB
opkg install kmod-usb-serial kmod-usb-serial-ftdi

# 測試 LoRa 模組
ls /dev/ttyUSB*   # USB 模組
ls /dev/spidev*   # SPI 模組
```

---

## 9. 設備樹覆蓋（SPI LoRa，進階）

如需從原始碼啟用 SPI LoRa 支援，在 OpenWRT DTS 檔中加入：

```dts
// arch/mips/dts/mt7621-myboard.dts
&spi0 {
    status = "okay";
    num-cs = <2>;

    lora@0 {
        compatible = "semtech,sx1276";
        reg = <0>;
        spi-max-frequency = <10000000>;
        reset-gpios = <&gpio 2 GPIO_ACTIVE_LOW>;
        interrupt-parent = <&gpio>;
        interrupts = <1 IRQ_TYPE_EDGE_RISING>;
    };
};
```

重新編譯 kernel：
```bash
make target/linux/compile
make -j$(nproc)
```

---

## 10. 已測試裝置清單

| 裝置 | OpenWRT 版本 | LoRa 介面 | 狀態 |
|------|------------|----------|------|
| GL.iNet GL-MT1300 | 23.05.3 | USB (RAK2247) | ✅ 可用 |
| Xiaomi Mi Router 3G | 23.05.3 | USB (RAK2247) | ✅ 可用 |
| Netgear R6220 | 23.05.3 | USB (RAK2247) | ✅ 可用 |
| 客製 MT7621 | 23.05.3 | SPI (SX1276) | ✅ 可用 |

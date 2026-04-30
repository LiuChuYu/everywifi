#!/bin/bash
# build_firmware.sh — Download OpenWRT and build EveryWifi firmware image
# Usage: bash scripts/build_firmware.sh [board]
# Example: bash scripts/build_firmware.sh glinet_gl-mt1300
set -e

BOARD="${1:-glinet_gl-mt1300}"
OPENWRT_VERSION="v23.05.3"
OPENWRT_DIR="$(pwd)/openwrt-build"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== EveryWifi Firmware Builder ==="
echo "Board:   $BOARD"
echo "OpenWRT: $OPENWRT_VERSION"
echo "Build dir: $OPENWRT_DIR"
echo ""

# --- Check dependencies ---
MISSING=()
for cmd in git make gcc g++ python3 wget curl file; do
    command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done
if [ ${#MISSING[@]} -ne 0 ]; then
    echo "ERROR: Missing build dependencies: ${MISSING[*]}"
    echo "Install with: sudo apt-get install build-essential git python3 wget curl"
    exit 1
fi

# --- Clone / update OpenWRT ---
if [ ! -d "$OPENWRT_DIR" ]; then
    echo "[1/5] Cloning OpenWRT $OPENWRT_VERSION..."
    git clone --depth=1 --branch "$OPENWRT_VERSION" \
        https://git.openwrt.org/openwrt/openwrt.git "$OPENWRT_DIR"
else
    echo "[1/5] OpenWRT source already present, skipping clone"
fi

cd "$OPENWRT_DIR"

# --- Update feeds ---
echo "[2/5] Updating feeds..."
./scripts/feeds update -a
./scripts/feeds install -a

# --- Apply .config ---
echo "[3/5] Applying EveryWifi .config..."
cp "$REPO_ROOT/firmware/config/openwrt_config" .config
# Enable specific board
sed -i "s/# CONFIG_TARGET_ramips_mt7621_DEVICE_${BOARD}.*$/CONFIG_TARGET_ramips_mt7621_DEVICE_${BOARD}=y/" .config
make defconfig

# --- Copy OpenWRT config files into rootfs overlay ---
mkdir -p files/etc/config
for f in network wireless firewall dhcp; do
    if [ -f "$REPO_ROOT/firmware/config/$f" ]; then
        cp "$REPO_ROOT/firmware/config/$f" "files/etc/config/$f"
        echo "  Copied $f → files/etc/config/$f"
    fi
done

# Copy EveryWifi app into firmware overlay
mkdir -p files/opt/everywifi
cp -r "$REPO_ROOT/src" files/opt/everywifi/
cp -r "$REPO_ROOT/scripts/install.sh" files/opt/everywifi/

# Init script
mkdir -p files/etc/init.d
cat > files/etc/init.d/everywifi << 'INITEOF'
#!/bin/sh /etc/rc.common
USE_PROCD=1
START=95
STOP=01

start_service() {
    mkdir -p /opt/everywifi/data
    procd_open_instance
    procd_set_param command python3 /opt/everywifi/src/main.py
    procd_set_param respawn 3600 5 0
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_set_param pidfile /var/run/everywifi.pid
    procd_close_instance
}
INITEOF
chmod +x files/etc/init.d/everywifi

# --- Build ---
echo "[4/5] Building firmware (this may take 60–180 minutes)..."
make -j"$(nproc)" V=s 2>&1 | tee build.log | grep -E "^(make|ERROR|WARNING)" || true

# --- Locate output ---
echo "[5/5] Locating firmware image..."
BIN_DIR="bin/targets/ramips/mt7621"
IMG=$(find "$BIN_DIR" -name "*sysupgrade*.bin" 2>/dev/null | head -1)

if [ -n "$IMG" ]; then
    echo ""
    echo "✅ Firmware built successfully!"
    echo "   Image: $OPENWRT_DIR/$IMG"
    echo ""
    echo "Flash with:"
    echo "  scp $IMG root@192.168.1.1:/tmp/"
    echo "  ssh root@192.168.1.1 'sysupgrade -n /tmp/$(basename $IMG)'"
else
    echo "❌ Build failed. Check $OPENWRT_DIR/build.log"
    exit 1
fi

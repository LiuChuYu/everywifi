#!/bin/sh
# install.sh — Install EveryWifi on a running OpenWRT device
# Run this script on the router after first boot:
#   scp -r everywifi root@192.168.1.1:/tmp/
#   ssh root@192.168.1.1 'sh /tmp/everywifi/scripts/install.sh'
set -e

INSTALL_DIR="/opt/everywifi"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== EveryWifi Installer ==="
echo "Source: $REPO_DIR"
echo "Target: $INSTALL_DIR"

# --- Update opkg ---
echo "[1/6] Updating package list..."
opkg update || echo "Warning: opkg update failed (offline?)"

# --- Install system dependencies ---
echo "[2/6] Installing system packages..."
opkg install python3 python3-asyncio python3-hashlib python3-logging \
    python3-sqlite3 python3-ssl python3-urllib python3-codecs \
    kmod-spi-dev kmod-usb-serial kmod-usb-serial-ftdi \
    wireguard-tools kmod-wireguard tc kmod-sched-core kmod-sched-htb \
    nftables kmod-nft-core kmod-nft-nat ip-full gpsd 2>/dev/null || true

# --- Install Python packages via pip (if pip available) ---
if command -v pip3 >/dev/null 2>&1; then
    echo "[3/6] Installing Python packages..."
    pip3 install pyserial --break-system-packages 2>/dev/null || \
        pip3 install pyserial 2>/dev/null || true
else
    echo "[3/6] pip3 not available, skipping Python packages"
fi

# --- Copy application files ---
echo "[4/6] Copying application files..."
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"
cp -r "$REPO_DIR/src" "$INSTALL_DIR/"

# --- Install init script ---
echo "[5/6] Installing init script..."
cat > /etc/init.d/everywifi << 'INITEOF'
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
chmod +x /etc/init.d/everywifi
/etc/init.d/everywifi enable

# --- Configure nftables sets for WiFi auth ---
echo "[6/6] Configuring nftables auth sets..."
nft add table inet filter 2>/dev/null || true
nft add set inet filter ewf_free '{ type ether_addr; }' 2>/dev/null || true
nft add set inet filter ewf_paid '{ type ether_addr; }' 2>/dev/null || true
# FORWARD rule: allow authenticated clients
nft add chain inet filter forward '{ type filter hook forward priority 0; }' 2>/dev/null || true
nft add rule inet filter forward ether saddr @ewf_paid accept 2>/dev/null || true
nft add rule inet filter forward ether saddr @ewf_free accept 2>/dev/null || true

echo ""
echo "✅ EveryWifi installed!"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/everywifi/src/config.py if needed"
echo "  2. Start service: /etc/init.d/everywifi start"
echo "  3. Check status:  curl http://127.0.0.1:8081/api/status"
echo "  4. View logs:     logread | grep everywifi"

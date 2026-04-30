#!/bin/bash
# setup_vpn.sh — Bootstrap WireGuard VPN for EveryWifi node
# Usage: bash scripts/setup_vpn.sh [hub_endpoint] [hub_pubkey] [node_vpn_ip]
# Example: bash scripts/setup_vpn.sh 1.2.3.4:51820 <hub_pubkey> 10.99.0.2
set -e

HUB_ENDPOINT="${1:-}"
HUB_PUBKEY="${2:-}"
NODE_VPN_IP="${3:-10.99.0.2}"
WG_IFACE="wg0"
WG_PORT=51820
KEY_DIR="/opt/everywifi/data/keys"

mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

# Generate keypair if not present
PRIV_KEY_FILE="$KEY_DIR/wg_private.key"
PUB_KEY_FILE="$KEY_DIR/wg_public.key"

if [ ! -f "$PRIV_KEY_FILE" ]; then
    echo "Generating WireGuard keypair..."
    wg genkey > "$PRIV_KEY_FILE"
    chmod 600 "$PRIV_KEY_FILE"
    wg pubkey < "$PRIV_KEY_FILE" > "$PUB_KEY_FILE"
fi

PRIV_KEY=$(cat "$PRIV_KEY_FILE")
PUB_KEY=$(cat "$PUB_KEY_FILE")

echo "Node public key: $PUB_KEY"
echo "Node VPN IP:     $NODE_VPN_IP/24"

# Write wg0.conf
mkdir -p /etc/wireguard
cat > /etc/wireguard/wg0.conf << EOF
[Interface]
PrivateKey = $PRIV_KEY
ListenPort = $WG_PORT
Address = $NODE_VPN_IP/24
EOF

if [ -n "$HUB_ENDPOINT" ] && [ -n "$HUB_PUBKEY" ]; then
    cat >> /etc/wireguard/wg0.conf << EOF

[Peer]
PublicKey = $HUB_PUBKEY
Endpoint = $HUB_ENDPOINT
AllowedIPs = 10.99.0.0/24
PersistentKeepalive = 25
EOF
    echo "Hub peer configured: $HUB_ENDPOINT"
fi

chmod 600 /etc/wireguard/wg0.conf

# Bring up interface
ip link add "$WG_IFACE" type wireguard 2>/dev/null || true
ip address add "$NODE_VPN_IP/24" dev "$WG_IFACE" 2>/dev/null || true
wg setconf "$WG_IFACE" /etc/wireguard/wg0.conf
ip link set "$WG_IFACE" up

echo ""
echo "✅ WireGuard VPN up!"
echo "   Interface: $WG_IFACE"
echo "   Address:   $NODE_VPN_IP/24"
echo ""
echo "Share this public key with the hub operator:"
echo "  $PUB_KEY"

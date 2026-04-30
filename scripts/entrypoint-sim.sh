#!/usr/bin/env bash
# entrypoint-sim.sh — container entry point for the docker-sim image.
# Reads /etc/everywifi/sim.conf, starts dnsmasq and hostapd.
set -euo pipefail

CONFIG="/etc/everywifi/sim.conf"

if [[ -f "${CONFIG}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG}"
fi

DNSMASQ_INTERFACE="${DNSMASQ_INTERFACE:-eth0}"
DNSMASQ_DHCP_RANGE="${DNSMASQ_DHCP_RANGE:-192.168.100.50,192.168.100.150,12h}"
DNSMASQ_DOMAIN="${DNSMASQ_DOMAIN:-everywifi.local}"
WAN_INTERFACE="${WAN_INTERFACE:-eth1}"
LAN_INTERFACE="${LAN_INTERFACE:-eth0}"
ENABLE_NAT="${ENABLE_NAT:-true}"

echo "==> everywifi-sim starting"
echo "    LAN  : ${LAN_INTERFACE}  (${DNSMASQ_DHCP_RANGE})"
echo "    WAN  : ${WAN_INTERFACE}"
echo "    SSID : ${HOSTAPD_SSID:-everywifi-sim}"

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# NAT (best-effort — may fail in restricted container runtimes)
if [[ "${ENABLE_NAT}" == "true" ]]; then
    iptables -t nat -A POSTROUTING -o "${WAN_INTERFACE}" -j MASQUERADE 2>/dev/null || \
        echo "WARN: iptables NAT rule not applied (may need --cap-add=NET_ADMIN)"
fi

# Start dnsmasq
dnsmasq \
    --interface="${DNSMASQ_INTERFACE}" \
    --dhcp-range="${DNSMASQ_DHCP_RANGE}" \
    --domain="${DNSMASQ_DOMAIN}" \
    --no-daemon &

echo "==> dnsmasq started (PID $!)"
echo "==> Simulation running. Press Ctrl+C to stop."

# Keep container alive; propagate signals
wait

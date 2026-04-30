"""
EveryWifi configuration.
All tuneable parameters live here or can be overridden by environment variables.
"""

import os

# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
LEDGER_DB_PATH: str = os.getenv(
    "EWF_LEDGER_DB", "/opt/everywifi/data/ledger.db"
)
# 1 EWF = 10^30 raw units (same scale as Nano's 10^30)
EWF_MULTIPLIER: int = 10 ** 30
# Tokens rewarded for a successful location verification
REWARD_PER_LOCATION_RAW: int = 10 * EWF_MULTIPLIER  # 10 EWF
# Bytes of high-speed traffic per 1 EWF
TRAFFIC_BYTES_PER_EWF: int = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# WiFi / captive portal
# ---------------------------------------------------------------------------
FREE_RATE_KBPS: int = int(os.getenv("EWF_FREE_RATE_KBPS", "1024"))  # 1 Mbps
DEFAULT_PAID_RATE_KBPS: int = int(
    os.getenv("EWF_PAID_RATE_KBPS", "10240")
)  # 10 Mbps
WIFI_IFACE: str = os.getenv("EWF_WIFI_IFACE", "wlan0")
LAN_IFACE: str = os.getenv("EWF_LAN_IFACE", "br-lan")
CAPTIVE_PORTAL_HOST: str = os.getenv("EWF_PORTAL_HOST", "192.168.10.1")
CAPTIVE_PORTAL_PORT: int = int(os.getenv("EWF_PORTAL_PORT", "8080"))
SESSION_TIMEOUT_SECONDS: int = int(
    os.getenv("EWF_SESSION_TIMEOUT", str(3600))
)  # 1 hour default

# ---------------------------------------------------------------------------
# LoRa
# ---------------------------------------------------------------------------
LORA_DEVICE: str = os.getenv("EWF_LORA_DEVICE", "/dev/ttyUSB0")
LORA_BAUD: int = int(os.getenv("EWF_LORA_BAUD", "115200"))
LORA_FREQ_MHZ: float = float(os.getenv("EWF_LORA_FREQ_MHZ", "868.1"))
LORA_SF: int = int(os.getenv("EWF_LORA_SF", "7"))  # Spreading factor
LORA_BW_KHZ: int = int(os.getenv("EWF_LORA_BW_KHZ", "125"))
# Minimum number of peer confirmations required for location reward
MIN_LOCATION_CONFIRMATIONS: int = int(
    os.getenv("EWF_MIN_CONFIRMATIONS", "3")
)
# RSSI tolerance window (dBm) for accepting a peer confirmation
RSSI_TOLERANCE_DBM: float = float(os.getenv("EWF_RSSI_TOLERANCE", "15.0"))

# ---------------------------------------------------------------------------
# P2P Gossip
# ---------------------------------------------------------------------------
P2P_PORT: int = int(os.getenv("EWF_P2P_PORT", "7777"))
BOOTSTRAP_PEERS: list[str] = [
    p.strip()
    for p in os.getenv("EWF_BOOTSTRAP_PEERS", "").split(",")
    if p.strip()
]
GOSSIP_INTERVAL: int = int(os.getenv("EWF_GOSSIP_INTERVAL", "10"))
GOSSIP_FANOUT: int = int(os.getenv("EWF_GOSSIP_FANOUT", "3"))
GOSSIP_MSG_TTL: int = int(os.getenv("EWF_GOSSIP_TTL", "5"))

# ---------------------------------------------------------------------------
# VPN (WireGuard)
# ---------------------------------------------------------------------------
WG_IFACE: str = os.getenv("EWF_WG_IFACE", "wg0")
WG_PORT: int = int(os.getenv("EWF_WG_PORT", "51820"))
WG_SUBNET: str = os.getenv("EWF_WG_SUBNET", "10.99.0.0/24")
WG_CONFIG_PATH: str = os.getenv(
    "EWF_WG_CONFIG", "/etc/wireguard/wg0.conf"
)

# ---------------------------------------------------------------------------
# API server
# ---------------------------------------------------------------------------
API_HOST: str = os.getenv("EWF_API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("EWF_API_PORT", "8081"))

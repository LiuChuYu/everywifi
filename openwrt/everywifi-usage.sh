#!/bin/sh
# everywifi-usage.sh
# OpenWrt 流量回報腳本：定期將已用流量回報給帳本 API。
#
# 建議放入 crontab，每 5 分鐘執行一次：
#   */5 * * * * /etc/everywifi/everywifi-usage.sh <token> <iface> [mac]
#
# 環境變數：
#   LEDGER_URL  帳本 API 的 base URL，預設 http://localhost:5000
#
# 依賴：
#   - ifconfig 或 /sys/class/net/<iface>/statistics/
#   - curl

LEDGER_URL="${LEDGER_URL:-http://localhost:5000}"
STATE_DIR="${STATE_DIR:-/tmp/everywifi}"

TOKEN="$1"
IFACE="${2:-br-lan}"
MAC="$3"

if [ -z "$TOKEN" ]; then
    echo "Usage: $0 <token> [iface] [mac_address]" >&2
    exit 1
fi

mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/bytes_${TOKEN}.last"

# 讀取目前網卡累積 RX+TX bytes（只計 RX 方向，即下載流量）
RX_BYTES=$(cat "/sys/class/net/$IFACE/statistics/rx_bytes" 2>/dev/null)
TX_BYTES=$(cat "/sys/class/net/$IFACE/statistics/tx_bytes" 2>/dev/null)

if [ -z "$RX_BYTES" ] || [ -z "$TX_BYTES" ]; then
    echo "Cannot read statistics for $IFACE" >&2
    exit 2
fi

TOTAL_BYTES=$((RX_BYTES + TX_BYTES))

# 計算與上次的差值
if [ -f "$STATE_FILE" ]; then
    LAST=$(cat "$STATE_FILE")
else
    LAST="$TOTAL_BYTES"
fi

DELTA=$((TOTAL_BYTES - LAST))

# 計數器重置（系統重開機）
if [ "$DELTA" -lt 0 ]; then
    DELTA="$TOTAL_BYTES"
fi

# 寫回目前值
echo "$TOTAL_BYTES" > "$STATE_FILE"

# 若差值為 0，不需要回報
if [ "$DELTA" -eq 0 ]; then
    exit 0
fi

# 回報給帳本 API
BODY="{\"token\":\"$TOKEN\",\"bytes_used\":$DELTA"
if [ -n "$MAC" ]; then
    BODY="$BODY,\"mac_address\":\"$MAC\""
fi
BODY="$BODY}"

RESPONSE=$(curl -s -X POST "$LEDGER_URL/usage/deduct" \
    -H "Content-Type: application/json" \
    -d "$BODY")

IS_ACTIVE=$(echo "$RESPONSE" | grep -o '"is_active":[a-z]*' | cut -d':' -f2)

if [ "$IS_ACTIVE" = "false" ]; then
    echo "QUOTA_EXCEEDED: user has run out of data/time" >&2
    # 通知 nodogsplash 踢出使用者（視 nodogsplash 版本調整指令）
    # ndsctl deauth "$MAC" 2>/dev/null || true
    exit 4
fi

exit 0

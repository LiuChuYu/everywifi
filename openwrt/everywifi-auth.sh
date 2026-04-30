#!/bin/sh
# everywifi-auth.sh
# OpenWrt 認證腳本：登入帳本 API 取得 token，傳給 nodogsplash 放行。
#
# 用法：
#   /etc/everywifi/everywifi-auth.sh <username> <password> <mac_address>
#
# 環境變數：
#   LEDGER_URL  帳本 API 的 base URL，預設 http://localhost:5000

LEDGER_URL="${LEDGER_URL:-http://localhost:5000}"

USERNAME="$1"
PASSWORD="$2"
MAC="$3"

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
    echo "Usage: $0 <username> <password> [mac_address]" >&2
    exit 1
fi

# --- 1. 登入取得 token ---
RESPONSE=$(curl -s -X POST "$LEDGER_URL/users/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")

TOKEN=$(echo "$RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo "AUTH_FAIL: login failed" >&2
    exit 2
fi

# --- 2. 驗證是否可上網 ---
AUTH=$(curl -s -X POST "$LEDGER_URL/auth" \
    -H "Content-Type: application/json" \
    -d "{\"token\":\"$TOKEN\",\"mac_address\":\"$MAC\"}")

ALLOWED=$(echo "$AUTH" | grep -o '"allowed":[a-z]*' | cut -d':' -f2)

if [ "$ALLOWED" = "true" ]; then
    echo "AUTH_OK"
    echo "TOKEN=$TOKEN"
    exit 0
else
    REASON=$(echo "$AUTH" | grep -o '"reason":"[^"]*"' | cut -d'"' -f4)
    echo "AUTH_FAIL: $REASON" >&2
    exit 3
fi

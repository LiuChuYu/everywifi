#!/bin/sh
# binauth.sh — nodogsplash BinAuth hook
# nodogsplash 在認證流程中呼叫此腳本。
# 參數：$1=method, $2=mac, $3=ip, $4=token(由 query string 傳入), ...
#
# 若認證成功，輸出「<upload_rate> <download_rate> <session_duration>」並 exit 0。
# 若認證失敗，exit 1。
#
# 文件：https://nodogsplash.readthedocs.io/en/latest/binauth.html

LEDGER_URL="${LEDGER_URL:-http://localhost:5000}"

METHOD="$1"
MAC="$2"
IP="$3"
TOKEN="$4"

case "$METHOD" in
auth_client)
    # 向帳本 API 驗證
    AUTH=$(curl -s -X POST "$LEDGER_URL/auth" \
        -H "Content-Type: application/json" \
        -d "{\"token\":\"$TOKEN\",\"mac_address\":\"$MAC\"}")

    ALLOWED=$(echo "$AUTH" | grep -o '"allowed":[a-z]*' | cut -d':' -f2)

    if [ "$ALLOWED" = "true" ]; then
        # 無限速；session 最長 3600 秒（之後 nodogsplash 會再呼叫一次 auth_client）
        echo "0 0 3600"
        exit 0
    else
        exit 1
    fi
    ;;

client_auth)
    # 認證成功後定期回報流量（此處簡單放行）
    exit 0
    ;;

client_deauth)
    # 使用者斷線，可在此記錄
    exit 0
    ;;

*)
    exit 0
    ;;
esac

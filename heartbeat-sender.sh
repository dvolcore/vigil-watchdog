#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# HEARTBEAT SENDER — Runs on Mac, sends heartbeats to Vigil
# ═══════════════════════════════════════════════════════════════════
# Install: Add to crontab to run every minute
# crontab -e
# * * * * * /Users/ralphd/.openclaw/sentinel/heartbeat-sender.sh
# ═══════════════════════════════════════════════════════════════════

# Configuration — UPDATE THIS
VIGIL_URL="${VIGIL_URL:-http://VIGIL_IP:8765/heartbeat}"

# Check Jordan (OpenClaw gateway) status
check_jordan() {
    if pgrep -f "openclaw.*gateway" > /dev/null 2>&1; then
        echo "ok"
    else
        echo "down"
    fi
}

# Check MiniMax status (if running as separate process)
check_minimax() {
    # MiniMax runs through OpenClaw, so check gateway
    check_jordan
}

# Get gateway details
get_details() {
    local pid uptime sessions
    pid=$(pgrep -f "openclaw.*gateway" | head -1)
    
    if [ -n "$pid" ]; then
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
        echo "{\"pid\": $pid, \"uptime\": \"$uptime\"}"
    else
        echo "{}"
    fi
}

# Send Jordan heartbeat
send_jordan_heartbeat() {
    local status=$(check_jordan)
    local details=$(get_details)
    
    curl -s -X POST "$VIGIL_URL" \
        -H "Content-Type: application/json" \
        -d "{
            \"source\": \"jordan\",
            \"status\": \"$status\",
            \"details\": $details,
            \"timestamp\": \"$(date -Iseconds)\"
        }" > /dev/null 2>&1
}

# Send MiniMax heartbeat  
send_minimax_heartbeat() {
    local status=$(check_minimax)
    
    curl -s -X POST "$VIGIL_URL" \
        -H "Content-Type: application/json" \
        -d "{
            \"source\": \"minimax\",
            \"status\": \"$status\",
            \"timestamp\": \"$(date -Iseconds)\"
        }" > /dev/null 2>&1
}

# Main
main() {
    send_jordan_heartbeat
    send_minimax_heartbeat
}

main "$@"

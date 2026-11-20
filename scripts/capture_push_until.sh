#!/usr/bin/env bash
set -euo pipefail

deadline=${1:?UTC deadline as Unix seconds required}
output=${2:?capture directory required}
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p -- "$output"
printf '%s\n' "$$" > "$output/supervisor.pid"

relay=
probe=
cleanup() {
    if [[ -n "$probe" ]]; then kill "$probe" 2>/dev/null || true; fi
    if [[ -n "$relay" ]]; then kill "$relay" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while (( $(date +%s) < deadline )); do
    "${ROBIN_RELAY_PYTHON:-python3}" "$root/examples/push_ws_relay.py" &
    relay=$!
    sleep 1
    remaining=$((deadline - $(date +%s)))
    if (( remaining < 1 )); then break; fi
    if (( remaining > 900 )); then remaining=900; fi
    segment=$(mktemp -d -- "$output/segment-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
    date -u +%FT%T.%NZ > "$segment/start-utc"
    ROBIN_PROBE_BINANCE=1 ROBIN_FEED_URL=ws://127.0.0.1:19647 \
        "$root/target/debug/examples/push_latency" "$remaining" > "$segment/capture.bin" &
    probe=$!
    status=0
    wait "$probe" || status=$?
    probe=
    kill "$relay" 2>/dev/null || true
    wait "$relay" 2>/dev/null || true
    relay=
    printf '%s\n' "$status" > "$segment/exit-status"
    if (( status == 0 )); then
        zstd -q -- "$segment/capture.bin"
    elif (( $(date +%s) < deadline )); then
        sleep 2
    fi
done
date -u +%FT%TZ > "$output/finished-utc"

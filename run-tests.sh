#!/bin/bash
# investment-debate-arena 测试统一入口（与 README.md 一致）
# 防重 + 资源限制
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p .test-runs
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG_FILE=".test-runs/run-$TS.log"
LOCK_FILE=".test-runs/.lock"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "SKIP: 另一个测试进程持有锁" >&2
  exit 75
fi

{
  echo "=== arena test run $TS ==="
  echo "load: $(cat /proc/loadavg)"
  echo
} >> "$LOG_FILE" 2>&1

PREFIX=(nice -n 19 ionice -c3 -n7)
if command -v systemd-run >/dev/null 2>&1 && [[ "$(id -u)" == "0" ]]; then
  PREFIX=(systemd-run --scope --quiet --collect \
    -p CPUQuota=70% -p MemoryMax=800M -p MemorySwapMax=0 \
    "${PREFIX[@]}")
fi

rc=0
"${PREFIX[@]}" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app \
  .venv/bin/python -m unittest discover -s tests "$@" \
  >> "$LOG_FILE" 2>&1 || rc=$?

# rotate logs: keep last 30
ls -1t .test-runs/run-*.log 2>/dev/null | tail -n +31 | xargs -r rm -f -- 2>/dev/null || true

echo "" >> "$LOG_FILE"
echo "=== finished exit=$rc at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG_FILE"
echo "log: $LOG_FILE"
tail -20 "$LOG_FILE"
exit $rc

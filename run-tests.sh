#!/bin/bash
# investment-debate-arena 测试统一入口（与 README.md 一致）
# 跨项目互斥: /var/lock/vps-tests/global.lock
# 单机资源约束: root → systemd-run scope；非 root → nice/ionice 软限额并明示
set -euo pipefail
cd "$(dirname "$0")"

GLOBAL_LOCK="/var/lock/vps-tests/global.lock"
mkdir -p .test-runs
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG_FILE=".test-runs/run-$TS.log"
touch "$LOG_FILE"
chmod 0660 "$LOG_FILE"

exec 200>"$GLOBAL_LOCK"
if ! flock -n 200; then
  echo "SKIP: 另一测试进程持有全局锁（$GLOBAL_LOCK），防重生效" >&2
  exit 75
fi

if [[ "$(id -u)" == "0" ]]; then
  if command -v systemd-run >/dev/null 2>&1; then
    PREFIX=(systemd-run --scope --quiet --collect
      -p CPUQuota=70% -p MemoryMax=800M -p MemorySwapMax=0
      nice -n 19 ionice -c3)
  else
    echo "FAIL: root 模式下 systemd-run 不可用，拒绝静默降级" >&2
    exit 9
  fi
else
  if ! command -v nice >/dev/null 2>&1; then
    echo "FAIL: nice 不可用，拒绝执行" >&2
    exit 9
  fi
  PREFIX=(nice -n 19)
  if command -v ionice >/dev/null 2>&1; then
    PREFIX+=(ionice -c3)
  else
    echo "WARN: ionice 不可用" >&2
  fi
  echo "WARN: 非 root 路径无 CPUQuota/MemoryMax 硬约束" >&2
fi

{
  echo "=== arena test run $TS ==="
  echo "user: $(id -un)($(id -u)) host: $(hostname)"
  echo "load: $(cat /proc/loadavg)"
  echo "prefix: ${PREFIX[*]}"
  echo
} >> "$LOG_FILE" 2>&1

rc=0
"${PREFIX[@]}" env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app \
  .venv/bin/python -m unittest discover -s tests "$@" \
  >> "$LOG_FILE" 2>&1 || rc=$?

ls -1t .test-runs/run-*.log 2>/dev/null | tail -n +31 | xargs -r rm -f -- 2>/dev/null || true

echo "" >> "$LOG_FILE"
echo "=== finished exit=$rc at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG_FILE"
if [[ "$(id -u)" == "0" ]]; then
  echo "resource-limits: CPUQuota=70% MemoryMax=800M (via systemd-run scope)" >> "$LOG_FILE"
fi
echo "log: $LOG_FILE"
tail -20 "$LOG_FILE"
exit $rc

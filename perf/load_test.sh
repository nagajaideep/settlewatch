#!/usr/bin/env bash
# Throughput of the client-blotter query (Q1) under concurrency, with and without its index.
# Random client per transaction so the test isn't served from one hot page.
# Usage: PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=... perf/load_test.sh [clients] [seconds]
set -euo pipefail
CLIENTS=${1:-16}
SECONDS_PER_RUN=${2:-20}
PGBENCH=$(command -v pgbench || echo /usr/lib/postgresql/16/bin/pgbench)
HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT=$(mktemp)
trap 'rm -f "$SCRIPT"' EXIT

cat > "$SCRIPT" <<'SQL'
\set c random(1, 5000)
SELECT * FROM trades WHERE client_id = 'CL' || lpad(:c::text, 5, '0') AND status = 'SETTLED'
ORDER BY trade_date DESC LIMIT 50;
SQL

run() {
  "$PGBENCH" -n -c "$CLIENTS" -j 4 -T "$SECONDS_PER_RUN" -f "$SCRIPT" 2>/dev/null \
    | grep -E "^(tps|latency average)" | sed 's/ (without initial connection time)//'
}

echo "== without idx_trades_client_status_date ($CLIENTS clients, ${SECONDS_PER_RUN}s)"
psql -X -q -c "DROP INDEX IF EXISTS idx_trades_client_status_date"
run | tee "$HERE/results/load_before.txt"

echo "== with idx_trades_client_status_date"
psql -X -q -c "CREATE INDEX IF NOT EXISTS idx_trades_client_status_date ON trades (client_id, status, trade_date DESC)"
run | tee "$HERE/results/load_after.txt"

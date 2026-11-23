# SQL performance tuning

How the indexes in `V2__performance_indexes.sql` were chosen, and what each one bought.

## Setup

| | |
|---|---|
| Data | 1,000,000 trades from `perf/seed_trades.sql`: 5,000 clients, 2,000 securities, 2 years of history |
| Status mix | 93.5% settled, 4.4% failed, 2.0% pending |
| Database | PostgreSQL 16, default config (`shared_buffers=128MB`, `work_mem=4MB`), 4 vCPU |
| Method | `EXPLAIN (ANALYZE, BUFFERS)`, 1 warm-up run then the median of 5 runs (`perf/benchmark.py`) |

Reproduce:

```bash
export PGHOST=localhost PGUSER=settlewatch PGPASSWORD=settlewatch PGDATABASE=settlewatch
psql -v rows=1000000 -f perf/seed_trades.sql   # ~30 s
python3 perf/benchmark.py                      # writes perf/results/
perf/load_test.sh 16 20                        # pgbench throughput test
```

## Results: single query, warm cache

| Query | Before | After | Speed-up | Buffers read |
|---|---:|---:|---:|---:|
| Q1 client blotter (client + status, newest first) | 45.3 ms | 0.22 ms | 210x | 20,481 → 53 |
| Q2 settlement engine pickup (due PENDING trades) | 44.7 ms | 0.93 ms | 48x | 20,481 → 427 |
| Q3 failed settlements in last 24h, by reason | 50.9 ms | 0.23 ms | 220x | 20,481 → 65 |
| Q4 client net positions | 51.6 ms | 0.71 ms | 72x | 20,479 → 181 |
| Q5 trades in one security | 37.9 ms | 0.33 ms | 116x | 20,481 → 104 |

Exact plans are in `perf/results/q*_before.txt` and `q*_after.txt`; `perf/results/RESULTS.md` is regenerated
on every run.

## Results: under concurrent load

Single-query timings understate the problem. Without an index every request scans all 20k pages
(160 MB), so concurrent requests compete for CPU and memory bandwidth. With `pgbench`, 16 clients ran the
Q1 blotter query for 20 seconds, each request for a random client:

| | Avg latency | Throughput |
|---|---:|---:|
| Without `idx_trades_client_status_date` | **523 ms** | 31 queries/s |
| With the index | **1.2 ms** | 12,937 queries/s |

That is a **~420x latency reduction** and a **~420x throughput gain**. The second row is the one an
on-call engineer sees on the latency dashboard.

## Index-by-index reasoning

**Q1 `idx_trades_client_status_date (client_id, status, trade_date DESC)`.** Equality columns come first
and the sort column last, so Postgres walks the index in order and stops after 50 rows. There is no sort
node and no full scan.

**Q2 `idx_trades_pending_settle_date (settlement_date) WHERE status = 'PENDING'`.** A partial index.
Only about 2% of rows are pending, so the index is **160 kB** while a full index would be about 30 MB.
Rows leave the index when they settle, so it stays small however large the table grows. The engine also
uses `FOR UPDATE SKIP LOCKED`, so several app instances can sweep at the same time without blocking each
other.

**Q3 `idx_trades_status_updated_at (status, updated_at DESC)`.** This serves the "failed in the last
N hours" query used by the dashboard, Prometheus alerts and the SRE bot. It also serves the ops
exception queue (`status = ? ORDER BY updated_at DESC`).

**Q4 positions.** A covering index `(client_id, isin) INCLUDE (side, quantity) WHERE status = 'SETTLED'`
was benchmarked first, aiming for an index-only scan. The planner kept choosing the Q1 index, because
there are only about 190 settled rows per client and a bitmap heap scan over them costs 0.7 ms. The covering
index cost **44 MB** plus write amplification on every insert and update, and it bought nothing, so it was
**removed**. Indexes are not free, and every one has to justify its write cost.

**Q5 `idx_trades_isin_trade_date (isin, trade_date DESC)`.** Security-level lookups for corporate actions
and ops investigations.

## Trade-offs

- Write cost: five secondary indexes add roughly 130 MB and an index update for every insert. Settlement
  updates touch `status` and `updated_at`, so they cannot be HOT updates. For a booking-heavy workload,
  consider dropping Q5 or moving ops queries to a read replica.
- The numbers are warm-cache. On cold storage the seq-scan cost rises with disk throughput, while the
  index paths read only 50–430 pages, so the gap would be larger, not smaller.
- `pg_stat_statements` is enabled in `docker-compose.yml`, so the SRE bot can report the slowest
  queries when a latency alert fires.

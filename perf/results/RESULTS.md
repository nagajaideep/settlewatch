# Query performance: before vs after indexing

- Dataset: **1,000,000 trades** (160 MB heap), PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
- Method: `EXPLAIN (ANALYZE, BUFFERS)`, 1 warm-up + median of 5 runs, warm cache
- Generated: 2026-11-23 13:21 UTC by `perf/benchmark.py`

| Query | Before | After | Speed-up | Buffers before → after | Plan before | Plan after |
|---|---:|---:|---:|---:|---|---|
| Q1 client blotter (client + status, newest first) | 45.3 ms | 0.216 ms | **210x** | 20,481 → 53 | Parallel Seq Scan | Index Scan using idx_trades_client_status_date |
| Q2 settlement engine pickup (due PENDING trades) | 44.7 ms | 0.932 ms | **48x** | 20,481 → 427 | Parallel Seq Scan | Index Scan using idx_trades_pending_settle_date |
| Q3 failed settlements in last 24h by reason | 50.9 ms | 0.231 ms | **220x** | 20,481 → 65 | Parallel Seq Scan | Index Scan using idx_trades_status_updated_at |
| Q4 client net positions | 51.6 ms | 0.713 ms | **72x** | 20,479 → 181 | Parallel Seq Scan | Bitmap Heap Scan, Bitmap Index Scan using idx_trades_client_status_date |
| Q5 trades in one security (ops / corporate actions) | 37.9 ms | 0.326 ms | **116x** | 20,481 → 104 | Parallel Seq Scan | Index Scan using idx_trades_isin_trade_date |

Index sizes: trades_pkey=21 MB, uq_trades_trade_ref=30 MB, idx_trades_client_status_date=36 MB, idx_trades_pending_settle_date=160 kB, idx_trades_status_updated_at=30 MB, idx_trades_isin_trade_date=32 MB

Full plans for each query are in this folder (`q*_before.txt`, `q*_after.txt`).

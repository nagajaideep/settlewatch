-- Indexes derived from EXPLAIN ANALYZE profiling against 1M trades.
-- Each index targets one hot query; see docs/performance.md for before/after plans.

-- Q1: client blotter - "show a client's trades in status X, newest first"
CREATE INDEX IF NOT EXISTS idx_trades_client_status_date
    ON trades (client_id, status, trade_date DESC);

-- Q2: settlement engine pickup - only PENDING rows matter, so a partial index stays tiny
CREATE INDEX IF NOT EXISTS idx_trades_pending_settle_date
    ON trades (settlement_date)
    WHERE status = 'PENDING';

-- Q3: failed settlements in a time window (monitoring, SRE bot, ops exception queue)
CREATE INDEX IF NOT EXISTS idx_trades_status_updated_at
    ON trades (status, updated_at DESC);

-- Q4: client positions reuse idx_trades_client_status_date (client_id, status prefix).
-- A covering index (client_id, isin) INCLUDE (side, quantity) WHERE status = 'SETTLED' was
-- benchmarked: the planner still preferred the composite index (~200 rows per client), so the
-- extra 44 MB and its write cost were not worth it. See docs/performance.md.

-- Q5: security-level lookups (corporate actions, ops queries by ISIN)
CREATE INDEX IF NOT EXISTS idx_trades_isin_trade_date
    ON trades (isin, trade_date DESC);

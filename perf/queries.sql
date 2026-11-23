-- The five hot queries the application runs. benchmark.py executes each block (separated by
-- lines starting with "-- name:") with EXPLAIN (ANALYZE, BUFFERS).

-- name: Q1 client blotter (client + status, newest first)
SELECT * FROM trades
WHERE client_id = 'CL01234' AND status = 'SETTLED'
ORDER BY trade_date DESC
LIMIT 50;

-- name: Q2 settlement engine pickup (due PENDING trades)
SELECT * FROM trades
WHERE status = 'PENDING' AND settlement_date <= current_date
ORDER BY settlement_date
LIMIT 500;

-- name: Q3 failed settlements in last 24h by reason
SELECT failure_reason, count(*)
FROM trades
WHERE status = 'FAILED' AND updated_at >= now() - interval '24 hours'
GROUP BY failure_reason;

-- name: Q4 client net positions
SELECT client_id, isin,
       SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) AS quantity,
       COUNT(*) AS trade_count
FROM trades
WHERE client_id = 'CL01234' AND status = 'SETTLED'
GROUP BY client_id, isin
HAVING SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) <> 0
ORDER BY isin;

-- name: Q5 trades in one security (ops / corporate actions)
SELECT * FROM trades
WHERE isin = 'US0000010422'
ORDER BY trade_date DESC
LIMIT 100;

-- Loads :rows mock trades (default 1,000,000) with a realistic custody distribution:
--   5,000 clients, 2,000 securities, two years of history,
--   ~95.5% settled / ~4.5% failed for past trades, ~2% still pending for upcoming dates.
-- Usage: psql -v rows=1000000 -f perf/seed_trades.sql
\set ON_ERROR_STOP on
\if :{?rows}
\else
  \set rows 1000000
\endif

SET synchronous_commit = off;
TRUNCATE trades RESTART IDENTITY;

INSERT INTO trades (trade_ref, client_id, isin, side, quantity, price, currency, counterparty,
                    trade_date, settlement_date, status, failure_reason, settled_at, created_at, updated_at)
SELECT
    'SEED-' || lpad(g::text, 9, '0'),
    'CL' || lpad((1 + floor(random() * 5000))::int::text, 5, '0'),
    isin,
    CASE WHEN random() < 0.55 THEN 'BUY' ELSE 'SELL' END,
    (1 + floor(random() * 5000))::numeric(18, 2),
    round((5 + random() * 495)::numeric, 6),
    (ARRAY['USD', 'USD', 'USD', 'EUR', 'GBP', 'JPY'])[1 + floor(random() * 6)::int],
    (ARRAY['BROKER-GS', 'BROKER-MS', 'BROKER-JPM', 'BROKER-CITI', 'BROKER-BARC', 'BROKER-UBS'])[1 + floor(random() * 6)::int],
    trade_date,
    trade_date + 1,
    status,
    CASE WHEN status = 'FAILED'
         THEN (ARRAY['INSUFFICIENT_SECURITIES', 'INSUFFICIENT_CASH', 'SSI_MISMATCH',
                     'COUNTERPARTY_UNMATCHED', 'MARKET_CLOSED'])[1 + floor(random() * 5)::int]
    END,
    CASE WHEN status = 'SETTLED' THEN (trade_date + 1) + time '16:00' END,
    trade_date + time '09:30' + random() * interval '7 hours',
    CASE WHEN status = 'PENDING' THEN trade_date + time '17:00'
         ELSE (trade_date + 1) + time '16:00' + random() * interval '2 hours' END
FROM (
    SELECT g,
           'US' || lpad(n::text, 9, '0') || (n % 10)::text AS isin,
           r,
           CASE WHEN r < 0.02 THEN current_date + (floor(random() * 3))::int - 1   -- pending, settles in coming days
                ELSE current_date - 2 - (floor(random() * 728))::int END AS trade_date,
           CASE WHEN r < 0.02 THEN 'PENDING'
                WHEN random() < 0.045 THEN 'FAILED'
                ELSE 'SETTLED' END AS status
    FROM (SELECT g, random() AS r, (1 + floor(random() * 2000))::int AS n
          FROM generate_series(1, :rows) AS g) s
) t;

-- keep the sequence in step with the seeded ids
SELECT setval('trades_id_seq', (SELECT max(id) FROM trades));
VACUUM ANALYZE trades;

SELECT status, count(*) FROM trades GROUP BY status ORDER BY status;

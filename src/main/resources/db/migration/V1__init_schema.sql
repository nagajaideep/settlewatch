-- SettleWatch core schema.
-- Deliberately ships with only the primary key and the business-key constraint.
-- Query-specific indexes are added in V2 after profiling with EXPLAIN ANALYZE
-- (see perf/ and docs/performance.md).

CREATE TABLE trades (
    id               BIGSERIAL PRIMARY KEY,
    trade_ref        VARCHAR(32)    NOT NULL,
    client_id        VARCHAR(16)    NOT NULL,
    isin             CHAR(12)       NOT NULL,
    side             VARCHAR(4)     NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity         NUMERIC(18, 2) NOT NULL CHECK (quantity > 0),
    price            NUMERIC(18, 6) NOT NULL CHECK (price > 0),
    currency         CHAR(3)        NOT NULL,
    counterparty     VARCHAR(64)    NOT NULL,
    trade_date       DATE           NOT NULL,
    settlement_date  DATE           NOT NULL,
    status           VARCHAR(10)    NOT NULL CHECK (status IN ('PENDING', 'SETTLED', 'FAILED')),
    failure_reason   VARCHAR(40),
    settled_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ    NOT NULL DEFAULT now(),
    version          BIGINT         NOT NULL DEFAULT 0,
    CONSTRAINT uq_trades_trade_ref UNIQUE (trade_ref),
    CONSTRAINT chk_settle_after_trade CHECK (settlement_date >= trade_date)
);

COMMENT ON TABLE trades IS 'Securities trades booked for custody clients and their settlement lifecycle';

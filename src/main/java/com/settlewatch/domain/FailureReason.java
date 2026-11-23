package com.settlewatch.domain;

/**
 * Common real-world causes of settlement fails at a custodian.
 */
public enum FailureReason {
    INSUFFICIENT_SECURITIES,
    INSUFFICIENT_CASH,
    SSI_MISMATCH,
    COUNTERPARTY_UNMATCHED,
    MARKET_CLOSED
}

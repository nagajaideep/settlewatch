package com.settlewatch.domain;

public class DuplicateTradeException extends RuntimeException {

    public DuplicateTradeException(String tradeRef) {
        super("Trade already exists: " + tradeRef);
    }
}

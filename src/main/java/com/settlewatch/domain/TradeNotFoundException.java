package com.settlewatch.domain;

public class TradeNotFoundException extends RuntimeException {

    public TradeNotFoundException(String tradeRef) {
        super("Trade not found: " + tradeRef);
    }
}

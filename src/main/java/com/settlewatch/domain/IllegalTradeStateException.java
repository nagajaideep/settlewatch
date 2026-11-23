package com.settlewatch.domain;

public class IllegalTradeStateException extends RuntimeException {

    public IllegalTradeStateException(String tradeRef, TradeStatus current, String action) {
        super("Trade %s is %s; cannot %s".formatted(tradeRef, current, action));
    }
}

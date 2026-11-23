package com.settlewatch.web;

import com.settlewatch.domain.FailureReason;
import com.settlewatch.domain.Side;
import com.settlewatch.domain.Trade;
import com.settlewatch.domain.TradeStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

public record TradeResponse(String tradeRef, String clientId, String isin, Side side, BigDecimal quantity,
                            BigDecimal price, BigDecimal notional, String currency, String counterparty,
                            LocalDate tradeDate, LocalDate settlementDate, TradeStatus status,
                            FailureReason failureReason, Instant settledAt, Instant createdAt, Instant updatedAt) {

    public static TradeResponse from(Trade t) {
        return new TradeResponse(t.getTradeRef(), t.getClientId(), t.getIsin(), t.getSide(), t.getQuantity(),
                t.getPrice(), t.notional(), t.getCurrency(), t.getCounterparty(), t.getTradeDate(),
                t.getSettlementDate(), t.getStatus(), t.getFailureReason(), t.getSettledAt(),
                t.getCreatedAt(), t.getUpdatedAt());
    }
}

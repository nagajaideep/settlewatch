package com.settlewatch.domain;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TradeTest {

    static Trade newTrade() {
        return new Trade("T1", "CL1", "US0378331005", Side.BUY, new BigDecimal("10"), new BigDecimal("2.5"),
                "USD", "CPTY", LocalDate.of(2026, 11, 20), LocalDate.of(2026, 11, 23));
    }

    @Test
    void newTradeIsPendingAndComputesNotional() {
        Trade t = newTrade();
        assertThat(t.getStatus()).isEqualTo(TradeStatus.PENDING);
        assertThat(t.notional()).isEqualByComparingTo("25");
    }

    @Test
    void settleSetsTimestamp() {
        Trade t = newTrade();
        Instant now = Instant.parse("2026-11-23T10:00:00Z");
        t.markSettled(now);
        assertThat(t.getStatus()).isEqualTo(TradeStatus.SETTLED);
        assertThat(t.getSettledAt()).isEqualTo(now);
    }

    @Test
    void cannotSettleTwice() {
        Trade t = newTrade();
        t.markSettled(Instant.now());
        assertThatThrownBy(() -> t.markSettled(Instant.now())).isInstanceOf(IllegalTradeStateException.class);
        assertThatThrownBy(() -> t.markFailed(FailureReason.SSI_MISMATCH)).isInstanceOf(IllegalTradeStateException.class);
    }

    @Test
    void failedTradeCanBeRetried() {
        Trade t = newTrade();
        t.markFailed(FailureReason.INSUFFICIENT_CASH);
        assertThat(t.getFailureReason()).isEqualTo(FailureReason.INSUFFICIENT_CASH);

        t.retry(LocalDate.of(2026, 11, 24));
        assertThat(t.getStatus()).isEqualTo(TradeStatus.PENDING);
        assertThat(t.getFailureReason()).isNull();
        assertThat(t.getSettlementDate()).isEqualTo(LocalDate.of(2026, 11, 24));
    }

    @Test
    void onlyFailedTradesCanBeRetried() {
        assertThatThrownBy(() -> newTrade().retry(LocalDate.now())).isInstanceOf(IllegalTradeStateException.class);
    }
}

package com.settlewatch.service;

import com.settlewatch.config.SettlementProperties;
import com.settlewatch.domain.DuplicateTradeException;
import com.settlewatch.domain.Side;
import com.settlewatch.domain.Trade;
import com.settlewatch.domain.TradeNotFoundException;
import com.settlewatch.repository.TradeRepository;
import com.settlewatch.web.BookTradeRequest;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class TradeServiceTest {

    // Friday 2026-11-20
    private final Clock clock = Clock.fixed(Instant.parse("2026-11-20T15:00:00Z"), ZoneOffset.UTC);
    private final TradeRepository repo = mock(TradeRepository.class);
    private final TradeService service = new TradeService(repo, new SettlementProperties(1000, 100, 0.0, 1),
            new SettlementMetrics(new SimpleMeterRegistry()), clock);

    private BookTradeRequest request(String ref) {
        return new BookTradeRequest(ref, "CL1", "US0378331005", Side.BUY, BigDecimal.TEN, BigDecimal.ONE,
                "USD", "CP", null, null);
    }

    @Test
    void bookingDefaultsToTodayAndTPlusOneBusinessDay() {
        when(repo.save(any(Trade.class))).thenAnswer(inv -> inv.getArgument(0));

        Trade t = service.book(request(null));

        assertThat(t.getTradeRef()).startsWith("TRD-");
        assertThat(t.getTradeDate()).isEqualTo(LocalDate.of(2026, 11, 20));
        assertThat(t.getSettlementDate()).isEqualTo(LocalDate.of(2026, 11, 23)); // skips the weekend
    }

    @Test
    void rejectsDuplicateTradeRef() {
        when(repo.existsByTradeRef("DUP")).thenReturn(true);
        assertThatThrownBy(() -> service.book(request("DUP"))).isInstanceOf(DuplicateTradeException.class);
        verify(repo, never()).save(any());
    }

    @Test
    void rejectsSettlementBeforeTradeDate() {
        var bad = new BookTradeRequest("X", "CL1", "US0378331005", Side.SELL, BigDecimal.TEN, BigDecimal.ONE,
                "USD", "CP", LocalDate.of(2026, 11, 20), LocalDate.of(2026, 11, 19));
        assertThatThrownBy(() -> service.book(bad)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void unknownTradeThrowsNotFound() {
        when(repo.findByTradeRef("NOPE")).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.get("NOPE")).isInstanceOf(TradeNotFoundException.class);
    }

    @Test
    void searchRequiresAFilter() {
        assertThatThrownBy(() -> service.search(null, null, null, 0, 10)).isInstanceOf(IllegalArgumentException.class);
    }
}

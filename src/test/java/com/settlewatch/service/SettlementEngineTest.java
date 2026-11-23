package com.settlewatch.service;

import com.settlewatch.config.SettlementProperties;
import com.settlewatch.domain.*;
import com.settlewatch.repository.TradeRepository;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.random.RandomGenerator;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.*;

class SettlementEngineTest {

    private final Clock clock = Clock.fixed(Instant.parse("2026-11-23T12:00:00Z"), ZoneOffset.UTC);
    private final TradeRepository repo = mock(TradeRepository.class);
    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final SettlementMetrics metrics = new SettlementMetrics(registry);
    private final ChaosService chaos = new ChaosService(mock(JdbcTemplate.class));
    private final SettlementProperties props = new SettlementProperties(1000, 500, 0.0, 1);

    private Trade trade(String ref) {
        return new Trade(ref, "CL1", "US0378331005", Side.BUY, BigDecimal.ONE, BigDecimal.TEN, "USD", "CP",
                LocalDate.of(2026, 11, 20), LocalDate.of(2026, 11, 23));
    }

    @BeforeEach
    void setUp() {
        when(repo.countDueForSettlement(any())).thenReturn(0L);
    }

    @Test
    void settlesAllDueTradesWhenFailureRateIsZero() {
        List<Trade> due = List.of(trade("A"), trade("B"));
        when(repo.lockDueForSettlement(LocalDate.of(2026, 11, 23), 500)).thenReturn(due);

        var engine = new SettlementEngine(repo, props, chaos, metrics, clock, new java.util.Random(42));
        var result = engine.sweep();

        assertThat(result.settled()).isEqualTo(2);
        assertThat(result.failed()).isZero();
        assertThat(due).allMatch(t -> t.getStatus() == TradeStatus.SETTLED);
        assertThat(registry.get("settlewatch.settlements").tag("outcome", "settled").counter().count()).isEqualTo(2);
    }

    @Test
    void chaosOverrideForcesFailuresWithReason() {
        List<Trade> due = List.of(trade("A"), trade("B"), trade("C"));
        when(repo.lockDueForSettlement(any(), anyInt())).thenReturn(due);
        chaos.setFailureRateOverride(1.0);

        var engine = new SettlementEngine(repo, props, chaos, metrics, clock, new java.util.Random(42));
        var result = engine.sweep();

        assertThat(result.failed()).isEqualTo(3);
        assertThat(due).allMatch(t -> t.getStatus() == TradeStatus.FAILED && t.getFailureReason() != null);
        double failedCount = registry.find("settlewatch.settlements").tag("outcome", "failed").counters()
                .stream().mapToDouble(c -> c.count()).sum();
        assertThat(failedCount).isEqualTo(3);
    }

    @Test
    void publishesRemainingBacklog() {
        when(repo.lockDueForSettlement(any(), anyInt())).thenReturn(List.of());
        when(repo.countDueForSettlement(any())).thenReturn(1234L);

        new SettlementEngine(repo, props, chaos, metrics, clock, new java.util.Random(42)).sweep();

        assertThat(registry.get("settlewatch.settlement.due.backlog").gauge().value()).isEqualTo(1234);
        verify(repo).flush();
    }
}

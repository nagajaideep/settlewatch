package com.settlewatch.service;

import com.settlewatch.domain.FailureReason;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Business metrics exported to Prometheus. Names become e.g.
 * settlewatch_settlements_total{outcome="failed",reason="SSI_MISMATCH"}.
 */
@Component
public class SettlementMetrics {

    private final Counter booked;
    private final Counter settled;
    private final Map<FailureReason, Counter> failed = new EnumMap<>(FailureReason.class);
    private final Timer sweepTimer;
    private final AtomicLong dueBacklog = new AtomicLong();

    public SettlementMetrics(MeterRegistry registry) {
        this.booked = Counter.builder("settlewatch.trades.booked")
                .description("Trades booked via the API")
                .register(registry);
        this.settled = Counter.builder("settlewatch.settlements")
                .description("Settlement attempts by outcome")
                .tag("outcome", "settled").tag("reason", "none")
                .register(registry);
        for (FailureReason reason : FailureReason.values()) {
            failed.put(reason, Counter.builder("settlewatch.settlements")
                    .description("Settlement attempts by outcome")
                    .tag("outcome", "failed").tag("reason", reason.name())
                    .register(registry));
        }
        this.sweepTimer = Timer.builder("settlewatch.settlement.sweep")
                .description("Duration of one settlement engine sweep")
                .publishPercentileHistogram()
                .register(registry);
        Gauge.builder("settlewatch.settlement.due.backlog", dueBacklog, AtomicLong::get)
                .description("PENDING trades whose settlement date has arrived")
                .register(registry);
    }

    public void tradeBooked() { booked.increment(); }
    public void settled() { settled.increment(); }
    public void failed(FailureReason reason) { failed.get(reason).increment(); }
    public Timer sweepTimer() { return sweepTimer; }
    public void dueBacklog(long value) { dueBacklog.set(value); }
}

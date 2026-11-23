package com.settlewatch.service;

import com.settlewatch.config.SettlementProperties;
import com.settlewatch.domain.FailureReason;
import com.settlewatch.domain.Trade;
import com.settlewatch.repository.TradeRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.random.RandomGenerator;

/**
 * Simulates the custodian's settlement run: each sweep takes PENDING trades whose
 * settlement date has arrived and either settles them or records a fail with a reason.
 */
@Service
public class SettlementEngine {

    private static final Logger log = LoggerFactory.getLogger(SettlementEngine.class);
    private static final FailureReason[] REASONS = FailureReason.values();

    private final TradeRepository trades;
    private final SettlementProperties props;
    private final ChaosService chaos;
    private final SettlementMetrics metrics;
    private final Clock clock;
    private final RandomGenerator random;

    public SettlementEngine(TradeRepository trades, SettlementProperties props, ChaosService chaos,
                            SettlementMetrics metrics, Clock clock, RandomGenerator settlementRandom) {
        this.trades = trades;
        this.props = props;
        this.chaos = chaos;
        this.metrics = metrics;
        this.clock = clock;
        this.random = settlementRandom;
    }

    @Transactional
    public SweepResult sweep() {
        LocalDate today = LocalDate.now(clock);
        List<Trade> due = trades.lockDueForSettlement(today, props.batchSize());
        double failureRate = chaos.failureRateOverride().orElse(props.failureRate());
        Instant now = clock.instant();

        int settledCount = 0;
        int failedCount = 0;
        for (Trade trade : due) {
            if (random.nextDouble() < failureRate) {
                FailureReason reason = REASONS[random.nextInt(REASONS.length)];
                trade.markFailed(reason);
                metrics.failed(reason);
                failedCount++;
                log.warn("Settlement FAILED trade={} client={} isin={} reason={}",
                        trade.getTradeRef(), trade.getClientId(), trade.getIsin(), reason);
            } else {
                trade.markSettled(now);
                metrics.settled();
                settledCount++;
            }
        }
        trades.flush();
        long backlog = trades.countDueForSettlement(today);
        metrics.dueBacklog(backlog);

        if (!due.isEmpty()) {
            log.info("Settlement sweep processed={} settled={} failed={} backlog={}",
                    due.size(), settledCount, failedCount, backlog);
        }
        return new SweepResult(due.size(), settledCount, failedCount);
    }

    public record SweepResult(int processed, int settled, int failed) {
    }
}

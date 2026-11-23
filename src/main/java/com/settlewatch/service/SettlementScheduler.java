package com.settlewatch.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Drives the settlement engine on a fixed delay. Kept separate from {@link SettlementEngine}
 * so the call goes through Spring's transactional proxy.
 */
@Component
@ConditionalOnProperty(name = "settlewatch.settlement.scheduler-enabled", havingValue = "true", matchIfMissing = true)
public class SettlementScheduler {

    private static final Logger log = LoggerFactory.getLogger(SettlementScheduler.class);

    private final SettlementEngine engine;
    private final SettlementMetrics metrics;

    public SettlementScheduler(SettlementEngine engine, SettlementMetrics metrics) {
        this.engine = engine;
        this.metrics = metrics;
    }

    @Scheduled(fixedDelayString = "${settlewatch.settlement.sweep-interval-ms}",
            initialDelayString = "${settlewatch.settlement.sweep-interval-ms}")
    public void run() {
        try {
            metrics.sweepTimer().record(engine::sweep);
        } catch (Exception e) {
            log.error("Settlement sweep failed: {}", e.getMessage(), e);
        }
    }
}

package com.settlewatch.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.OptionalDouble;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Fault injection for demos and game days. Each fault maps to a Prometheus alert,
 * which lets the SRE bot be exercised end to end:
 *   failure rate override -> SettlementFailureSpike
 *   API latency           -> HighApiLatency
 *   connection hog        -> DbConnectionPoolSaturated
 */
@Service
public class ChaosService {

    private static final Logger log = LoggerFactory.getLogger(ChaosService.class);

    private final JdbcTemplate jdbc;
    private final AtomicReference<Double> failureRateOverride = new AtomicReference<>();
    private final AtomicLong apiLatencyMs = new AtomicLong();
    private final AtomicInteger hoggedConnections = new AtomicInteger();
    private final ExecutorService hogPool = Executors.newVirtualThreadPerTaskExecutor();

    public ChaosService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public OptionalDouble failureRateOverride() {
        Double v = failureRateOverride.get();
        return v == null ? OptionalDouble.empty() : OptionalDouble.of(v);
    }

    public void setFailureRateOverride(Double rate) {
        if (rate != null && (rate < 0 || rate > 1)) {
            throw new IllegalArgumentException("failureRate must be between 0 and 1");
        }
        failureRateOverride.set(rate);
        log.warn("CHAOS settlement failure rate override set to {}", rate);
    }

    public long apiLatencyMs() {
        return apiLatencyMs.get();
    }

    public void setApiLatencyMs(long ms) {
        if (ms < 0 || ms > 30_000) {
            throw new IllegalArgumentException("latencyMs must be between 0 and 30000");
        }
        apiLatencyMs.set(ms);
        log.warn("CHAOS API latency injection set to {} ms", ms);
    }

    /** Occupies {@code connections} pooled DB connections with pg_sleep for {@code seconds}. */
    public void hogConnections(int connections, int seconds) {
        if (connections < 1 || connections > 50 || seconds < 1 || seconds > 600) {
            throw new IllegalArgumentException("connections 1-50, seconds 1-600");
        }
        log.warn("CHAOS hogging {} DB connections for {}s", connections, seconds);
        for (int i = 0; i < connections; i++) {
            hogPool.submit(() -> {
                hoggedConnections.incrementAndGet();
                try {
                    jdbc.execute("SELECT pg_sleep(" + seconds + ")");
                } catch (Exception e) {
                    log.error("CHAOS connection hog ended with error: {}", e.getMessage());
                } finally {
                    hoggedConnections.decrementAndGet();
                }
            });
        }
    }

    public int hoggedConnections() {
        return hoggedConnections.get();
    }

    public void reset() {
        failureRateOverride.set(null);
        apiLatencyMs.set(0);
        log.warn("CHAOS reset: all injected faults cleared (running connection hogs finish on their own)");
    }
}

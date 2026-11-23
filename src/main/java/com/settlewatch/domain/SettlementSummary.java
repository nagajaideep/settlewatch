package com.settlewatch.domain;

import java.util.Map;

public record SettlementSummary(long pending, long settled, long failed, long dueNow,
                                Map<String, Long> failuresByReasonLast24h) {

    public long total() {
        return pending + settled + failed;
    }

    public double failRatePercent() {
        long done = settled + failed;
        return done == 0 ? 0.0 : (failed * 100.0) / done;
    }
}

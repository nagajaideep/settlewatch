package com.settlewatch.config;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "settlewatch.settlement")
public record SettlementProperties(
        @Min(100) long sweepIntervalMs,
        @Min(1) int batchSize,
        @DecimalMin("0.0") @DecimalMax("1.0") double failureRate,
        @Min(0) int settlementCycleDays) {
}

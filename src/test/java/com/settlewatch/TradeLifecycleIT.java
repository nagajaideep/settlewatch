package com.settlewatch;

import com.settlewatch.service.SettlementEngine;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/** Full stack against a real PostgreSQL (Flyway migrations, native queries, locking). */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers(disabledWithoutDocker = true)
@TestPropertySource(properties = {
        "settlewatch.settlement.scheduler-enabled=false",
        "settlewatch.settlement.failure-rate=0.0",
        "logging.file.name=target/it.log"
})
class TradeLifecycleIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    TestRestTemplate http;
    @Autowired
    SettlementEngine engine;

    @Test
    @SuppressWarnings("unchecked")
    void bookSettleAndReportPosition() {
        Map<String, Object> buy = Map.of("clientId", "CLIT", "isin", "US0378331005", "side", "BUY",
                "quantity", 150, "price", 190.25, "currency", "USD", "counterparty", "CP",
                "tradeDate", "2026-01-05", "settlementDate", "2026-01-06");
        Map<String, Object> sell = Map.of("clientId", "CLIT", "isin", "US0378331005", "side", "SELL",
                "quantity", 50, "price", 191, "currency", "USD", "counterparty", "CP",
                "tradeDate", "2026-01-05", "settlementDate", "2026-01-06");

        ResponseEntity<Map> created = http.postForEntity("/api/trades", buy, Map.class);
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        http.postForEntity("/api/trades", sell, Map.class);

        var result = engine.sweep();
        assertThat(result.settled()).isEqualTo(2);

        List<Map<String, Object>> positions = http.getForObject("/api/clients/CLIT/positions", List.class);
        assertThat(positions).hasSize(1);
        assertThat(((Number) positions.get(0).get("quantity")).doubleValue()).isEqualTo(100.0);

        Map<String, Object> summary = http.getForObject("/api/settlements/summary", Map.class);
        assertThat(((Number) summary.get("settled")).intValue()).isEqualTo(2);
    }
}

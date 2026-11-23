package com.settlewatch.domain;

import java.math.BigDecimal;

/** Net settled holding of one security for one client. */
public record Position(String clientId, String isin, BigDecimal quantity, long tradeCount) {
}

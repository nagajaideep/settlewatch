package com.settlewatch.web;

import com.settlewatch.domain.Side;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.time.LocalDate;

public record BookTradeRequest(
        @Size(max = 32) String tradeRef,
        @NotBlank @Size(max = 16) String clientId,
        @NotBlank @Pattern(regexp = "^[A-Z]{2}[A-Z0-9]{9}[0-9]$", message = "must be a 12-character ISIN") String isin,
        @NotNull Side side,
        @NotNull @Positive @Digits(integer = 16, fraction = 2) BigDecimal quantity,
        @NotNull @Positive @Digits(integer = 12, fraction = 6) BigDecimal price,
        @NotBlank @Pattern(regexp = "^[A-Z]{3}$", message = "must be an ISO 4217 code") String currency,
        @NotBlank @Size(max = 64) String counterparty,
        LocalDate tradeDate,
        LocalDate settlementDate) {
}

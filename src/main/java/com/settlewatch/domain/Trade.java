package com.settlewatch.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

@Entity
@Table(name = "trades")
public class Trade {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "trade_ref", nullable = false, unique = true, length = 32)
    private String tradeRef;

    @Column(name = "client_id", nullable = false, length = 16)
    private String clientId;

    @Column(nullable = false, length = 12, columnDefinition = "bpchar(12)")
    private String isin;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 4)
    private Side side;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal quantity;

    @Column(nullable = false, precision = 18, scale = 6)
    private BigDecimal price;

    @Column(nullable = false, length = 3, columnDefinition = "bpchar(3)")
    private String currency;

    @Column(nullable = false, length = 64)
    private String counterparty;

    @Column(name = "trade_date", nullable = false)
    private LocalDate tradeDate;

    @Column(name = "settlement_date", nullable = false)
    private LocalDate settlementDate;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private TradeStatus status;

    @Enumerated(EnumType.STRING)
    @Column(name = "failure_reason", length = 40)
    private FailureReason failureReason;

    @Column(name = "settled_at")
    private Instant settledAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected Trade() {
        // for JPA
    }

    public Trade(String tradeRef, String clientId, String isin, Side side, BigDecimal quantity,
                 BigDecimal price, String currency, String counterparty,
                 LocalDate tradeDate, LocalDate settlementDate) {
        this.tradeRef = tradeRef;
        this.clientId = clientId;
        this.isin = isin;
        this.side = side;
        this.quantity = quantity;
        this.price = price;
        this.currency = currency;
        this.counterparty = counterparty;
        this.tradeDate = tradeDate;
        this.settlementDate = settlementDate;
        this.status = TradeStatus.PENDING;
    }

    @PrePersist
    void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    public void markSettled(Instant when) {
        requirePending();
        this.status = TradeStatus.SETTLED;
        this.failureReason = null;
        this.settledAt = when;
    }

    public void markFailed(FailureReason reason) {
        requirePending();
        this.status = TradeStatus.FAILED;
        this.failureReason = reason;
    }

    /** Ops can re-queue a failed trade once the break is fixed (e.g. SSIs corrected). */
    public void retry(LocalDate newSettlementDate) {
        if (status != TradeStatus.FAILED) {
            throw new IllegalTradeStateException(tradeRef, status, "retry");
        }
        this.status = TradeStatus.PENDING;
        this.failureReason = null;
        this.settlementDate = newSettlementDate;
    }

    private void requirePending() {
        if (status != TradeStatus.PENDING) {
            throw new IllegalTradeStateException(tradeRef, status, "settle/fail");
        }
    }

    public BigDecimal notional() {
        return quantity.multiply(price);
    }

    public Long getId() { return id; }
    public String getTradeRef() { return tradeRef; }
    public String getClientId() { return clientId; }
    public String getIsin() { return isin; }
    public Side getSide() { return side; }
    public BigDecimal getQuantity() { return quantity; }
    public BigDecimal getPrice() { return price; }
    public String getCurrency() { return currency; }
    public String getCounterparty() { return counterparty; }
    public LocalDate getTradeDate() { return tradeDate; }
    public LocalDate getSettlementDate() { return settlementDate; }
    public TradeStatus getStatus() { return status; }
    public FailureReason getFailureReason() { return failureReason; }
    public Instant getSettledAt() { return settledAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}

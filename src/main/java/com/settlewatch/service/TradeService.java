package com.settlewatch.service;

import com.settlewatch.config.SettlementProperties;
import com.settlewatch.domain.*;
import com.settlewatch.repository.TradeRepository;
import com.settlewatch.web.BookTradeRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Duration;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

@Service
public class TradeService {

    private static final Logger log = LoggerFactory.getLogger(TradeService.class);
    private static final int MAX_PAGE_SIZE = 200;

    private final TradeRepository trades;
    private final SettlementProperties props;
    private final SettlementMetrics metrics;
    private final Clock clock;

    public TradeService(TradeRepository trades, SettlementProperties props, SettlementMetrics metrics, Clock clock) {
        this.trades = trades;
        this.props = props;
        this.metrics = metrics;
        this.clock = clock;
    }

    @Transactional
    public Trade book(BookTradeRequest req) {
        String ref = req.tradeRef() != null && !req.tradeRef().isBlank()
                ? req.tradeRef()
                : "TRD-" + UUID.randomUUID().toString().substring(0, 13).toUpperCase();
        if (trades.existsByTradeRef(ref)) {
            throw new DuplicateTradeException(ref);
        }
        LocalDate tradeDate = req.tradeDate() != null ? req.tradeDate() : LocalDate.now(clock);
        LocalDate settlementDate = req.settlementDate() != null
                ? req.settlementDate()
                : BusinessDays.add(tradeDate, props.settlementCycleDays());
        if (settlementDate.isBefore(tradeDate)) {
            throw new IllegalArgumentException("settlementDate must not be before tradeDate");
        }
        Trade trade = trades.save(new Trade(ref, req.clientId(), req.isin(), req.side(), req.quantity(),
                req.price(), req.currency(), req.counterparty(), tradeDate, settlementDate));
        metrics.tradeBooked();
        log.info("Booked trade={} client={} isin={} side={} qty={} settle={}",
                ref, req.clientId(), req.isin(), req.side(), req.quantity(), settlementDate);
        return trade;
    }

    @Transactional(readOnly = true)
    public Trade get(String tradeRef) {
        return trades.findByTradeRef(tradeRef).orElseThrow(() -> new TradeNotFoundException(tradeRef));
    }

    @Transactional(readOnly = true)
    public Page<Trade> search(String clientId, TradeStatus status, String isin, int page, int size) {
        PageRequest pr = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
        if (clientId != null && status != null) {
            return trades.findByClientIdAndStatusOrderByTradeDateDesc(clientId, status, pr);
        }
        if (clientId != null) {
            return trades.findByClientIdOrderByTradeDateDesc(clientId, pr);
        }
        if (isin != null) {
            return trades.findByIsinOrderByTradeDateDesc(isin, pr);
        }
        if (status != null) {
            return trades.findByStatusOrderByUpdatedAtDesc(status, pr);
        }
        throw new IllegalArgumentException("Provide at least one of clientId, status or isin");
    }

    @Transactional
    public Trade forceSettle(String tradeRef) {
        Trade t = get(tradeRef);
        t.markSettled(clock.instant());
        metrics.settled();
        log.info("Manually settled trade={}", tradeRef);
        return t;
    }

    @Transactional
    public Trade forceFail(String tradeRef, FailureReason reason) {
        Trade t = get(tradeRef);
        t.markFailed(reason);
        metrics.failed(reason);
        log.warn("Settlement FAILED trade={} client={} isin={} reason={} (manual)",
                tradeRef, t.getClientId(), t.getIsin(), reason);
        return t;
    }

    @Transactional
    public Trade retry(String tradeRef) {
        Trade t = get(tradeRef);
        t.retry(LocalDate.now(clock));
        log.info("Re-queued failed trade={} for settlement", tradeRef);
        return t;
    }

    @Transactional(readOnly = true)
    public List<Position> positions(String clientId) {
        return trades.positionsForClient(clientId).stream()
                .map(p -> new Position(p.getClientId(), p.getIsin(), p.getQuantity(), p.getTradeCount()))
                .toList();
    }

    @Transactional(readOnly = true)
    public SettlementSummary summary() {
        Map<String, Long> byStatus = new TreeMap<>();
        trades.countByStatus().forEach(s -> byStatus.put(s.getStatus(), s.getCnt()));
        Map<String, Long> reasons = new TreeMap<>();
        trades.failuresByReasonSince(clock.instant().minus(Duration.ofHours(24)))
                .forEach(r -> reasons.put(r.getReason(), r.getCnt()));
        return new SettlementSummary(
                byStatus.getOrDefault("PENDING", 0L),
                byStatus.getOrDefault("SETTLED", 0L),
                byStatus.getOrDefault("FAILED", 0L),
                trades.countDueForSettlement(LocalDate.now(clock)),
                reasons);
    }
}

package com.settlewatch.repository;

import com.settlewatch.domain.Trade;
import com.settlewatch.domain.TradeStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

public interface TradeRepository extends JpaRepository<Trade, Long> {

    Optional<Trade> findByTradeRef(String tradeRef);

    boolean existsByTradeRef(String tradeRef);

    /** Q1 - client blotter. Served by idx_trades_client_status_date. */
    Page<Trade> findByClientIdAndStatusOrderByTradeDateDesc(String clientId, TradeStatus status, Pageable pageable);

    Page<Trade> findByClientIdOrderByTradeDateDesc(String clientId, Pageable pageable);

    Page<Trade> findByStatusOrderByUpdatedAtDesc(TradeStatus status, Pageable pageable);

    /** Q5 - security lookup. Served by idx_trades_isin_trade_date. */
    Page<Trade> findByIsinOrderByTradeDateDesc(String isin, Pageable pageable);

    /**
     * Q2 - settlement engine pickup. SKIP LOCKED lets several app instances sweep
     * concurrently without double-processing. Served by idx_trades_pending_settle_date.
     */
    @Query(value = """
            SELECT * FROM trades
            WHERE status = 'PENDING' AND settlement_date <= :asOf
            ORDER BY settlement_date
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
            """, nativeQuery = true)
    List<Trade> lockDueForSettlement(@Param("asOf") LocalDate asOf, @Param("limit") int limit);

    @Query(value = "SELECT count(*) FROM trades WHERE status = 'PENDING' AND settlement_date <= :asOf",
            nativeQuery = true)
    long countDueForSettlement(@Param("asOf") LocalDate asOf);

    /** Q4 - net settled positions. Served by idx_trades_client_status_date. */
    @Query(value = """
            SELECT client_id                                                        AS clientId,
                   isin                                                             AS isin,
                   SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)     AS quantity,
                   COUNT(*)                                                         AS tradeCount
            FROM trades
            WHERE client_id = :clientId AND status = 'SETTLED'
            GROUP BY client_id, isin
            HAVING SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) <> 0
            ORDER BY isin
            """, nativeQuery = true)
    List<PositionView> positionsForClient(@Param("clientId") String clientId);

    /** Q3 - failed settlements in a window, grouped by reason. Served by idx_trades_status_updated_at. */
    @Query(value = """
            SELECT failure_reason AS reason, COUNT(*) AS cnt
            FROM trades
            WHERE status = 'FAILED' AND updated_at >= :since
            GROUP BY failure_reason
            """, nativeQuery = true)
    List<ReasonCount> failuresByReasonSince(@Param("since") Instant since);

    @Query(value = "SELECT status AS status, COUNT(*) AS cnt FROM trades GROUP BY status", nativeQuery = true)
    List<StatusCount> countByStatus();

    interface PositionView {
        String getClientId();
        String getIsin();
        java.math.BigDecimal getQuantity();
        long getTradeCount();
    }

    interface ReasonCount {
        String getReason();
        long getCnt();
    }

    interface StatusCount {
        String getStatus();
        long getCnt();
    }
}

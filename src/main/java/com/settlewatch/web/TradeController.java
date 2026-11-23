package com.settlewatch.web;

import com.settlewatch.domain.FailureReason;
import com.settlewatch.domain.Position;
import com.settlewatch.domain.SettlementSummary;
import com.settlewatch.domain.TradeStatus;
import com.settlewatch.service.SettlementEngine;
import com.settlewatch.service.TradeService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

import java.util.List;

@RestController
@RequestMapping("/api")
public class TradeController {

    private final TradeService service;
    private final SettlementEngine engine;

    public TradeController(TradeService service, SettlementEngine engine) {
        this.service = service;
        this.engine = engine;
    }

    @PostMapping("/trades")
    public ResponseEntity<TradeResponse> book(@Valid @RequestBody BookTradeRequest request) {
        TradeResponse body = TradeResponse.from(service.book(request));
        return ResponseEntity
                .created(ServletUriComponentsBuilder.fromCurrentRequest()
                        .path("/{ref}").buildAndExpand(body.tradeRef()).toUri())
                .body(body);
    }

    @GetMapping("/trades/{tradeRef}")
    public TradeResponse get(@PathVariable String tradeRef) {
        return TradeResponse.from(service.get(tradeRef));
    }

    @GetMapping("/trades")
    public PageResponse<TradeResponse> search(@RequestParam(required = false) String clientId,
                                              @RequestParam(required = false) TradeStatus status,
                                              @RequestParam(required = false) String isin,
                                              @RequestParam(defaultValue = "0") int page,
                                              @RequestParam(defaultValue = "50") int size) {
        Page<TradeResponse> result = service.search(clientId, status, isin, page, size).map(TradeResponse::from);
        return PageResponse.from(result);
    }

    @PostMapping("/trades/{tradeRef}/settle")
    public TradeResponse settle(@PathVariable String tradeRef) {
        return TradeResponse.from(service.forceSettle(tradeRef));
    }

    @PostMapping("/trades/{tradeRef}/fail")
    public TradeResponse fail(@PathVariable String tradeRef, @RequestParam FailureReason reason) {
        return TradeResponse.from(service.forceFail(tradeRef, reason));
    }

    @PostMapping("/trades/{tradeRef}/retry")
    public TradeResponse retry(@PathVariable String tradeRef) {
        return TradeResponse.from(service.retry(tradeRef));
    }

    @GetMapping("/clients/{clientId}/positions")
    public List<Position> positions(@PathVariable String clientId) {
        return service.positions(clientId);
    }

    @GetMapping("/settlements/summary")
    public SettlementSummary summary() {
        return service.summary();
    }

    /** Triggers one settlement sweep immediately instead of waiting for the scheduler. */
    @PostMapping("/settlements/sweep")
    @ResponseStatus(HttpStatus.OK)
    public SettlementEngine.SweepResult sweepNow() {
        return engine.sweep();
    }
}

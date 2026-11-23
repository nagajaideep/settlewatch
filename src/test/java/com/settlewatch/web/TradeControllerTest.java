package com.settlewatch.web;

import com.settlewatch.domain.*;
import com.settlewatch.service.ChaosService;
import com.settlewatch.service.SettlementEngine;
import com.settlewatch.service.TradeService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(TradeController.class)
class TradeControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    TradeService service;
    @MockitoBean
    SettlementEngine engine;
    @MockitoBean
    ChaosService chaos;

    private Trade sample() {
        return new Trade("TRD-1", "CL1", "US0378331005", Side.BUY, new BigDecimal("100"), new BigDecimal("10"),
                "USD", "CP", LocalDate.of(2026, 11, 20), LocalDate.of(2026, 11, 23));
    }

    @Test
    void bookReturns201WithLocation() throws Exception {
        when(service.book(any())).thenReturn(sample());
        mvc.perform(post("/api/trades").contentType(MediaType.APPLICATION_JSON).content("""
                        {"clientId":"CL1","isin":"US0378331005","side":"BUY","quantity":100,
                         "price":10,"currency":"USD","counterparty":"CP"}"""))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "http://localhost/api/trades/TRD-1"))
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.notional").value(1000));
    }

    @Test
    void invalidBookingReturns400WithFieldErrors() throws Exception {
        mvc.perform(post("/api/trades").contentType(MediaType.APPLICATION_JSON).content("""
                        {"clientId":"CL1","isin":"NOT-AN-ISIN","side":"BUY","quantity":0,
                         "price":10,"currency":"usd","counterparty":"CP"}"""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors.isin").exists())
                .andExpect(jsonPath("$.errors.quantity").exists())
                .andExpect(jsonPath("$.errors.currency").exists());
    }

    @Test
    void unknownTradeReturns404() throws Exception {
        when(service.get("X")).thenThrow(new TradeNotFoundException("X"));
        mvc.perform(get("/api/trades/X")).andExpect(status().isNotFound());
    }

    @Test
    void illegalTransitionReturns409() throws Exception {
        when(service.retry("TRD-1")).thenThrow(new IllegalTradeStateException("TRD-1", TradeStatus.SETTLED, "retry"));
        mvc.perform(post("/api/trades/TRD-1/retry")).andExpect(status().isConflict());
    }

    @Test
    void positionsEndpoint() throws Exception {
        when(service.positions("CL1")).thenReturn(List.of(new Position("CL1", "US0378331005", new BigDecimal("50"), 3)));
        mvc.perform(get("/api/clients/CL1/positions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].quantity").value(50))
                .andExpect(jsonPath("$[0].tradeCount").value(3));
    }
}

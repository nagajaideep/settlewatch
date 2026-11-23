package com.settlewatch.web;

import com.settlewatch.domain.Side;
import com.settlewatch.domain.TradeStatus;
import com.settlewatch.service.TradeService;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.math.BigDecimal;

/** Server-rendered operations console (Thymeleaf). */
@Controller
public class UiController {

    private final TradeService service;

    public UiController(TradeService service) {
        this.service = service;
    }

    @GetMapping("/")
    public String dashboard(Model model) {
        model.addAttribute("summary", service.summary());
        model.addAttribute("failed", service.search(null, TradeStatus.FAILED, null, 0, 15).getContent());
        model.addAttribute("pending", service.search(null, TradeStatus.PENDING, null, 0, 15).getContent());
        return "dashboard";
    }

    @GetMapping("/clients")
    public String client(@RequestParam(required = false) String clientId, Model model) {
        if (clientId != null && !clientId.isBlank()) {
            String id = clientId.trim();
            model.addAttribute("clientId", id);
            model.addAttribute("positions", service.positions(id));
            model.addAttribute("trades", service.search(id, null, null, 0, 25).getContent());
        }
        return "client";
    }

    @GetMapping("/book")
    public String bookForm(Model model) {
        model.addAttribute("sides", Side.values());
        return "book";
    }

    @PostMapping("/book")
    public String book(@RequestParam String clientId, @RequestParam String isin, @RequestParam Side side,
                       @RequestParam BigDecimal quantity, @RequestParam BigDecimal price,
                       @RequestParam String currency, @RequestParam String counterparty,
                       RedirectAttributes redirect) {
        try {
            var trade = service.book(new BookTradeRequest(null, clientId.trim(), isin.trim().toUpperCase(), side,
                    quantity, price, currency.trim().toUpperCase(), counterparty.trim(), null, null));
            redirect.addFlashAttribute("message", "Booked " + trade.getTradeRef()
                    + ", settles " + trade.getSettlementDate());
        } catch (RuntimeException e) {
            redirect.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/book";
    }

    @PostMapping("/trades/retry")
    public String retry(@RequestParam String tradeRef, RedirectAttributes redirect) {
        try {
            service.retry(tradeRef);
            redirect.addFlashAttribute("message", "Re-queued " + tradeRef);
        } catch (RuntimeException e) {
            redirect.addFlashAttribute("error", e.getMessage());
        }
        return "redirect:/";
    }
}

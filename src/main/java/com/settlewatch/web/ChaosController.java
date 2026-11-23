package com.settlewatch.web;

import com.settlewatch.service.ChaosService;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;

/** Fault injection endpoints used to rehearse incidents. Disable in real production. */
@RestController
@RequestMapping("/api/admin/chaos")
public class ChaosController {

    private final ChaosService chaos;

    public ChaosController(ChaosService chaos) {
        this.chaos = chaos;
    }

    @GetMapping
    public Map<String, Object> status() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("failureRateOverride", chaos.failureRateOverride().isPresent()
                ? chaos.failureRateOverride().getAsDouble() : null);
        m.put("apiLatencyMs", chaos.apiLatencyMs());
        m.put("hoggedConnections", chaos.hoggedConnections());
        return m;
    }

    @PostMapping("/failure-rate")
    public Map<String, Object> failureRate(@RequestParam double rate) {
        chaos.setFailureRateOverride(rate);
        return status();
    }

    @PostMapping("/latency")
    public Map<String, Object> latency(@RequestParam long ms) {
        chaos.setApiLatencyMs(ms);
        return status();
    }

    @PostMapping("/hog-connections")
    public Map<String, Object> hog(@RequestParam(defaultValue = "8") int connections,
                                   @RequestParam(defaultValue = "120") int seconds) {
        chaos.hogConnections(connections, seconds);
        return status();
    }

    @PostMapping("/reset")
    public Map<String, Object> reset() {
        chaos.reset();
        return status();
    }
}

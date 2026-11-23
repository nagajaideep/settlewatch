#!/usr/bin/env python3
"""Generates docker/grafana/dashboards/settlewatch.json. Edit here, not in the JSON."""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
API = 'uri=~"/api/.*", uri!~"/api/admin.*"'
panels = []
_id = 0


def panel(kind, title, targets, x, y, w, h, unit=None, extra=None, desc=None):
    global _id
    _id += 1
    p = {
        "id": _id, "type": kind, "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [{"datasource": DS, "refId": chr(65 + i), "expr": e, "legendFormat": l}
                    for i, (e, l) in enumerate(targets)],
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
    }
    if desc:
        p["description"] = desc
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    if kind == "timeseries":
        p["fieldConfig"]["defaults"]["custom"] = {"lineWidth": 2, "fillOpacity": 8, "showPoints": "never"}
        p["options"] = {"legend": {"displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi", "sort": "desc"}}
    if extra:
        for k, v in extra.items():
            if k == "defaults":
                p["fieldConfig"]["defaults"].update(v)
            else:
                p[k] = v
    panels.append(p)


def thresholds(*steps):
    return {"defaults": {"thresholds": {"mode": "absolute", "steps": [
        {"color": c, "value": v} for v, c in steps]}, "color": {"mode": "thresholds"}}}


def row(title, y):
    global _id
    _id += 1
    panels.append({"id": _id, "type": "row", "title": title, "collapsed": False,
                   "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})


# --- headline stats ---
row("Overview", 0)
panel("stat", "Failed settlements (last 1h)",
      [('sum(increase(settlewatch_settlements_total{outcome="failed"}[1h]))', "")], 0, 1, 5, 4,
      extra=thresholds((None, "green"), (50, "orange"), (200, "red")))
panel("stat", "Settlement fail rate (10m)",
      [('sum(increase(settlewatch_settlements_total{outcome="failed"}[10m])) / '
        'clamp_min(sum(increase(settlewatch_settlements_total[10m])), 1)', "")], 5, 1, 5, 4, unit="percentunit",
      extra=thresholds((None, "green"), (0.05, "orange"), (0.10, "red")))
panel("stat", "API p95 latency (5m)",
      [(f'histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{{{API}}}[5m])))', "")],
      10, 1, 5, 4, unit="s", extra=thresholds((None, "green"), (0.25, "orange"), (0.5, "red")))
panel("stat", "DB pool in use",
      [("max(hikaricp_connections_active / hikaricp_connections_max)", "")], 15, 1, 4, 4, unit="percentunit",
      extra=thresholds((None, "green"), (0.6, "orange"), (0.8, "red")))
panel("stat", "Firing alerts",
      [('count(ALERTS{alertstate="firing"}) or vector(0)', "")], 19, 1, 5, 4,
      extra=thresholds((None, "green"), (1, "red")))

# --- settlements ---
row("Settlements", 5)
panel("timeseries", "Failed settlements per hour, by reason",
      [('sum by (reason) (increase(settlewatch_settlements_total{outcome="failed"}[1h]))', "{{reason}}")],
      0, 6, 12, 8, extra={"defaults": {"custom": {"drawStyle": "bars", "stacking": {"mode": "normal"},
                                                  "fillOpacity": 70, "lineWidth": 1}}},
      desc="Rolling 1h count of fails, stacked by failure reason")
panel("timeseries", "Settlement throughput",
      [('sum by (outcome) (rate(settlewatch_settlements_total[5m])) * 60', "{{outcome}}")],
      12, 6, 12, 8, unit="short", desc="Settlement attempts per minute")
panel("timeseries", "Due backlog (pending trades past settlement date)",
      [("settlewatch_settlement_due_backlog", "backlog")], 0, 14, 12, 7, unit="short")
panel("timeseries", "Settlement sweep duration",
      [("histogram_quantile(0.95, sum by (le) (rate(settlewatch_settlement_sweep_seconds_bucket[5m])))", "p95"),
       ("histogram_quantile(0.50, sum by (le) (rate(settlewatch_settlement_sweep_seconds_bucket[5m])))", "p50")],
      12, 14, 12, 7, unit="s")

# --- API ---
row("Trade API", 21)
panel("timeseries", "API latency p95 by endpoint",
      [(f'histogram_quantile(0.95, sum by (le, method, uri) (rate(http_server_requests_seconds_bucket{{{API}}}[5m])))',
        "{{method}} {{uri}}")], 0, 22, 12, 8, unit="s")
panel("timeseries", "API request rate by status",
      [(f'sum by (status) (rate(http_server_requests_seconds_count{{{API}}}[5m]))', "{{status}}")],
      12, 22, 12, 8, unit="reqps")

# --- DB ---
row("Database connections", 30)
panel("timeseries", "Hikari connection pool",
      [("sum(hikaricp_connections_active)", "active"), ("sum(hikaricp_connections_idle)", "idle"),
       ("sum(hikaricp_connections_pending)", "waiting threads"), ("sum(hikaricp_connections_max)", "max")],
      0, 31, 12, 8, unit="short")
panel("timeseries", "Connection acquire time p95",
      [("histogram_quantile(0.95, sum by (le) (rate(hikaricp_connections_acquire_seconds_bucket[5m]))) "
        "or max(hikaricp_connections_acquire_seconds_max)", "acquire")],
      12, 31, 12, 8, unit="s")

# --- JVM ---
row("JVM", 39)
panel("timeseries", "Heap used", [('sum(jvm_memory_used_bytes{area="heap"})', "used"),
                                  ('sum(jvm_memory_max_bytes{area="heap"})', "max")], 0, 40, 12, 7, unit="bytes")
panel("timeseries", "GC pause time", [("sum(rate(jvm_gc_pause_seconds_sum[5m]))", "gc seconds/s")],
      12, 40, 12, 7, unit="s")

dashboard = {
    "uid": "settlewatch-main",
    "title": "SettleWatch: Settlement Operations",
    "tags": ["settlewatch", "sre"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "10s",
    "time": {"from": "now-1h", "to": "now"},
    "panels": panels,
    "annotations": {"list": [{
        "name": "Alerts", "datasource": DS, "enable": True, "iconColor": "red",
        "expr": 'ALERTS{alertstate="firing"}', "titleFormat": "{{alertname}}", "step": "30s",
    }]},
}

out = Path(__file__).resolve().parent.parent / "docker/grafana/dashboards/settlewatch.json"
out.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"wrote {out} ({len(panels)} panels)")

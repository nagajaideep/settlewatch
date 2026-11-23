"""
Rule-based diagnosis. Each alert type has an analyser that looks at the collected evidence,
names the most likely cause and proposes next actions, the way an on-call engineer's first
ten minutes would go. The analysers are pure functions of their inputs, so they are unit-tested
without any running infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .collectors import Collector, Result

# ITIL priority matrix: (impact, urgency) -> priority
PRIORITY_MATRIX = {
    ("high", "high"): "P1", ("high", "medium"): "P2", ("medium", "high"): "P2",
    ("medium", "medium"): "P3", ("high", "low"): "P3", ("low", "high"): "P3",
    ("medium", "low"): "P4", ("low", "medium"): "P4", ("low", "low"): "P5",
}

FAILURE_REASON_GUIDE = {
    "SSI_MISMATCH": ("Standing settlement instructions don't match between us and the counterparty "
                     "(often after a static-data change).",
                     "Compare SSIs in the reference-data system against the counterparty's; check "
                     "recent static-data changes."),
    "INSUFFICIENT_SECURITIES": ("Delivering account is short the securities (failed upstream receipt, "
                                "unrecalled loan or corporate action).",
                                "Check inbound receipts and securities-lending recalls for the affected ISINs."),
    "INSUFFICIENT_CASH": ("Paying account lacks funding for DVP settlement.",
                          "Check client cash balances and FX/funding instructions for affected clients."),
    "COUNTERPARTY_UNMATCHED": ("Counterparty has not affirmed or matched the trade in the matching platform.",
                               "Contact the counterparty ops desk and check the matching platform's queue."),
    "MARKET_CLOSED": ("Settlement attempted outside market/CSD operating hours or on a holiday.",
                      "Verify the holiday calendar and CSD operating schedule for the settlement date."),
}


@dataclass
class Diagnosis:
    alertname: str
    title: str
    impact: str
    urgency: str
    probable_cause: str
    evidence: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    fault_injection_active: bool = False

    @property
    def priority(self) -> str:
        return PRIORITY_MATRIX.get((self.impact, self.urgency), "P3")


# ---------------------------------------------------------------- pure analysers

def analyse_failures(breakdown: dict, chaos: dict | None) -> tuple[str, list[str], list[str]]:
    """Returns (probable_cause, evidence, actions) for a settlement failure spike."""
    reasons = breakdown.get("by_reason") or []
    failed = sum(r["n"] for r in reasons)
    settled = breakdown.get("settled", 0)
    minutes = breakdown.get("minutes", 30)
    evidence = [f"{failed} fails vs {settled} successful settlements in the last {minutes} min "
                f"(fail rate {failed / max(failed + settled, 1):.1%}, baseline ~3%)."]
    actions: list[str] = []

    if failed == 0:
        return ("No failed trades found in the database for the window; the alert may be stale or the "
                "metrics and database disagree.", evidence,
                ["Confirm the alert against the Grafana settlement panels.", "Check the app is writing to "
                 "the expected database."])

    top_reason, top_n = reasons[0]["key"], reasons[0]["n"]
    share = top_n / failed
    cptys = breakdown.get("by_counterparty") or []
    isins = breakdown.get("by_isin") or []
    evidence.append("Fails by reason: " + ", ".join(f"{r['key']}={r['n']}" for r in reasons))
    if cptys:
        evidence.append("Top counterparties: " + ", ".join(f"{c['key']}={c['n']}" for c in cptys))

    causes = []
    if share >= 0.6:
        explanation, action = FAILURE_REASON_GUIDE.get(top_reason, ("Unrecognised failure reason.", ""))
        causes.append(f"{share:.0%} of fails are {top_reason}: {explanation}")
        if action:
            actions.append(action)
    else:
        causes.append("Fails are spread across reasons (top is "
                      f"{top_reason} at {share:.0%}), which points to a systemic issue rather than one "
                      "data problem: settlement engine, CSD connectivity or market-wide disruption.")
        actions.append("Check CSD/agent connectivity and the settlement engine logs for errors.")

    if cptys and failed >= 10 and cptys[0]["n"] / failed >= 0.5:
        causes.append(f"Fails are concentrated on counterparty {cptys[0]['key']} "
                      f"({cptys[0]['n'] / failed:.0%}).")
        actions.append(f"Contact {cptys[0]['key']} operations; consider holding new trades with them.")
    if isins and failed >= 10 and isins[0]["n"] / failed >= 0.3:
        causes.append(f"Security {isins[0]['key']} accounts for {isins[0]['n'] / failed:.0%} of fails; "
                      "check for a corporate action or a restricted security.")

    if chaos and chaos.get("failureRateOverride") is not None:
        causes.insert(0, f"Fault injection is ACTIVE (failureRateOverride={chaos['failureRateOverride']}). "
                         "This is a drill, not a market event.")
        actions.insert(0, "If this is not a planned game day, reset it: POST /api/admin/chaos/reset")

    actions += ["Re-queue fixed trades via POST /api/trades/{ref}/retry once the root cause is fixed.",
                "Notify the client service team about affected clients if fails persist past cut-off."]
    return " ".join(causes), evidence, actions


def analyse_latency(p95_by_uri: list[tuple[dict, float]], slow: list[dict], missing_idx: list[str],
                    pool_pending: float | None, chaos: dict | None,
                    scan_stats: dict | None) -> tuple[str, list[str], list[str]]:
    evidence, actions, causes = [], [], []
    worst = sorted(p95_by_uri, key=lambda x: x[1], reverse=True)[:5]
    if worst:
        evidence.append("Slowest endpoints (p95): " + ", ".join(
            f"{m.get('method', '')} {m.get('uri', '?')}={v * 1000:.0f}ms" for m, v in worst))

    slow_db = [q for q in slow if float(q.get("mean_ms", 0)) >= 100]
    if missing_idx:
        causes.append("Expected indexes are MISSING: " + ", ".join(missing_idx) + ". Queries that "
                      "depended on them are now full table scans (see docs/performance.md).")
        actions.append("Recreate them: psql -f src/main/resources/db/migration/V2__performance_indexes.sql "
                       "(use CREATE INDEX CONCURRENTLY on a live system).")
    if slow_db:
        top = slow_db[0]
        causes.append(f"Database is the bottleneck: slowest statement averages {top['mean_ms']} ms over "
                      f"{top['calls']} calls.")
        actions.append("Run EXPLAIN (ANALYZE, BUFFERS) on the top statement below and check for seq scans.")
    if scan_stats and scan_stats.get("seq_scan") and scan_stats.get("idx_scan") is not None:
        ratio = scan_stats["seq_scan"] / max(scan_stats["seq_scan"] + scan_stats["idx_scan"], 1)
        evidence.append(f"trades table: {scan_stats['seq_scan']:,} seq scans vs {scan_stats['idx_scan']:,} "
                        f"index scans ({ratio:.1%} sequential) since stats reset.")
    if pool_pending and pool_pending > 0:
        causes.append(f"{pool_pending:.0f} request threads are waiting for a DB connection, so latency "
                      "includes connection queueing.")
        actions.append("See the DbConnectionPoolSaturated runbook; look for long-running queries.")
    if chaos and chaos.get("apiLatencyMs"):
        causes.insert(0, f"Fault injection is ACTIVE: {chaos['apiLatencyMs']} ms of latency is added to "
                         "every API call. This is a drill.")
        actions.insert(0, "If unplanned, reset it: POST /api/admin/chaos/reset")
    if not causes:
        causes.append("The database looks healthy (no slow statements, indexes present, no pool wait), so "
                      "the latency is most likely in the application tier: GC pauses, CPU saturation or a "
                      "slow downstream call.")
        actions += ["Check the JVM GC and heap panels in Grafana.", "Take a thread dump: jcmd <pid> Thread.print"]
    return " ".join(causes), evidence, actions


def analyse_pool(long_running: list[dict], states: list[dict], active_ratio: float | None,
                 chaos: dict | None) -> tuple[str, list[str], list[str]]:
    evidence, actions = [], []
    if active_ratio is not None:
        evidence.append(f"Hikari pool utilisation {active_ratio:.0%}.")
    if states:
        evidence.append("DB sessions: " + ", ".join(
            f"{s['state'] or 'n/a'}={s['connections']}" for s in states))
    sleepers = [q for q in long_running if "pg_sleep" in (q.get("query") or "")]
    if long_running:
        oldest = long_running[0]
        cause = (f"{len(long_running)} queries have been running for 5s or more (oldest {oldest['seconds']}s, "
                 f"pid {oldest['pid']}). They hold pool connections and starve normal traffic.")
        actions += ["Identify the caller of the long-running statements below.",
                    "If safe, cancel them: SELECT pg_cancel_backend(<pid>); escalate to "
                    "pg_terminate_backend only if cancel fails.",
                    "Add a statement_timeout for the application role so this can't recur silently."]
    else:
        cause = ("No long-running queries, so the pool is busy with many short requests: likely a traffic "
                 "surge or a pool that is too small for the load.")
        actions += ["Compare request rate against the baseline in Grafana.",
                    "Consider raising DB_POOL_SIZE (keep it below Postgres max_connections / instances)."]
    if sleepers or (chaos and chaos.get("hoggedConnections")):
        cause = ("Fault injection is ACTIVE: the connection-hog drill is holding connections with pg_sleep. "
                 + cause)
    return cause, evidence, actions


# ---------------------------------------------------------------- orchestration

def _record(res: Result, d: Diagnosis, default=None):
    if not res.ok:
        d.gaps.append(res.error)
        return default
    return res.value


def diagnose(alert: dict, c: Collector) -> Diagnosis:
    labels = alert.get("labels", {})
    name = labels.get("alertname", "UnknownAlert")
    severity = labels.get("severity", "warning")
    summary = alert.get("annotations", {}).get("summary", name)
    d = Diagnosis(alertname=name, title=summary,
                  impact="high" if severity == "critical" else "medium",
                  urgency="high" if severity == "critical" else "medium",
                  probable_cause="")
    chaos = _record(c.chaos_status(), d)
    d.fault_injection_active = bool(chaos and (chaos.get("failureRateOverride") is not None
                                               or chaos.get("apiLatencyMs") or chaos.get("hoggedConnections")))

    handler: Callable[[Diagnosis, Collector, dict | None], None] = HANDLERS.get(name, _generic)
    handler(d, c, chaos)
    d.logs = _record(c.recent_log_lines(), d, []) or []
    return d


def _failures(d: Diagnosis, c: Collector, chaos):
    b = _record(c.failure_breakdown(30), d)
    if b is None:
        d.probable_cause = "Could not query the trades table; see the data gaps below."
        return
    d.probable_cause, d.evidence, d.actions = analyse_failures(b, chaos)
    d.tables["Sample failed trades"] = b["sample"]


def _latency(d: Diagnosis, c: Collector, chaos):
    p95 = _record(c.prom('histogram_quantile(0.95, sum by (le, method, uri) '
                         '(rate(http_server_requests_seconds_bucket{uri=~"/api/.*",uri!~"/api/admin.*"}[5m])))'),
                  d, []) or []
    p95 = [(m, v) for m, v in p95 if v == v]  # drop NaN
    slow = _record(c.slow_queries(), d, []) or []
    missing = _record(c.missing_indexes(), d, []) or []
    pending = _record(c.prom_scalar("max(hikaricp_connections_pending)"), d)
    scans = _record(c.table_scan_stats(), d, []) or []
    d.probable_cause, d.evidence, d.actions = analyse_latency(p95, slow, missing, pending, chaos,
                                                              scans[0] if scans else None)
    d.tables["Top statements by mean time (pg_stat_statements)"] = slow


def _pool(d: Diagnosis, c: Collector, chaos):
    long_running = _record(c.long_running_queries(5), d, []) or []
    states = _record(c.connection_states(), d, []) or []
    ratio = _record(c.prom_scalar("max(hikaricp_connections_active / hikaricp_connections_max)"), d)
    d.probable_cause, d.evidence, d.actions = analyse_pool(long_running, states, ratio, chaos)
    d.tables["Long-running queries (pg_stat_activity)"] = long_running


def _backlog(d: Diagnosis, c: Collector, chaos):
    backlog = _record(c.prom_scalar("settlewatch_settlement_due_backlog"), d)
    sweep = _record(c.prom_scalar("histogram_quantile(0.95, sum by (le) "
                                  "(rate(settlewatch_settlement_sweep_seconds_bucket[5m])))"), d)
    d.evidence = [f"Due backlog: {backlog:,.0f} trades." if backlog is not None else "Backlog unknown.",
                  f"Sweep p95 duration: {sweep:.2f}s." if sweep else "No recent sweeps recorded."]
    d.probable_cause = ("The settlement engine is not draining due trades fast enough: sweeps are slow or "
                        "not running, or booking volume is above sweep capacity (batch size x frequency).")
    d.actions = ["Check the engine logs for 'Settlement sweep failed'.",
                 "Trigger a manual sweep: POST /api/settlements/sweep",
                 "Raise SETTLEMENT_BATCH_SIZE or run more instances (SKIP LOCKED makes this safe)."]


def _down(d: Diagnosis, c: Collector, chaos):
    d.probable_cause = "Prometheus cannot scrape the application: the process is down, restarting or hung."
    d.evidence = ["Alert fired from the `up` metric."]
    d.actions = ["Check the container: docker compose ps app / docker compose logs --tail=200 app",
                 "Look for OutOfMemoryError or failed Flyway migration at startup.",
                 "Restart: docker compose restart app"]


def _generic(d: Diagnosis, c: Collector, chaos):
    d.probable_cause = "No specific playbook for this alert; recent errors and DB state are attached."
    d.tables["Top statements by mean time (pg_stat_statements)"] = _record(c.slow_queries(), d, []) or []


HANDLERS = {
    "SettlementFailureSpike": _failures,
    "HighApiLatency": _latency,
    "DbConnectionPoolSaturated": _pool,
    "SettlementBacklogGrowing": _backlog,
    "SettleWatchDown": _down,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

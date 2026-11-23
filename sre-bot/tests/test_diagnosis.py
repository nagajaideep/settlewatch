from sre_bot.collectors import Result
from sre_bot.diagnosis import Diagnosis, analyse_failures, analyse_latency, analyse_pool, diagnose


def breakdown(reasons, cptys=(), isins=(), settled=500):
    return {"minutes": 30, "settled": settled, "sample": [],
            "by_reason": [{"key": k, "n": n} for k, n in reasons],
            "by_counterparty": [{"key": k, "n": n} for k, n in cptys],
            "by_isin": [{"key": k, "n": n} for k, n in isins]}


def test_dominant_reason_is_named_with_specific_action():
    cause, evidence, actions = analyse_failures(
        breakdown([("SSI_MISMATCH", 80), ("INSUFFICIENT_CASH", 10)]), chaos={"failureRateOverride": None})
    assert "SSI_MISMATCH" in cause and "instructions" in cause
    assert any("SSIs" in a for a in actions)
    assert "15.3%" in evidence[0]  # 90 / (90 + 500)


def test_spread_reasons_point_to_systemic_issue():
    cause, _, actions = analyse_failures(
        breakdown([("SSI_MISMATCH", 20), ("INSUFFICIENT_CASH", 20), ("MARKET_CLOSED", 19),
                   ("COUNTERPARTY_UNMATCHED", 18)]), chaos=None)
    assert "systemic" in cause
    assert any("connectivity" in a for a in actions)


def test_counterparty_concentration_detected():
    cause, _, actions = analyse_failures(
        breakdown([("COUNTERPARTY_UNMATCHED", 40)], cptys=[("BROKER-UBS", 35), ("BROKER-GS", 5)]), chaos=None)
    assert "BROKER-UBS" in cause
    assert any("BROKER-UBS" in a for a in actions)


def test_fault_injection_flagged_as_drill():
    cause, _, actions = analyse_failures(breakdown([("SSI_MISMATCH", 50)]), chaos={"failureRateOverride": 0.5})
    assert cause.startswith("Fault injection is ACTIVE")
    assert "chaos/reset" in actions[0]


def test_no_fails_in_db_reports_mismatch():
    cause, _, _ = analyse_failures(breakdown([]), chaos=None)
    assert "stale" in cause


def test_latency_missing_index_is_primary_cause():
    cause, _, actions = analyse_latency(
        p95_by_uri=[({"method": "GET", "uri": "/api/trades"}, 1.8)],
        slow=[{"query": "SELECT * FROM trades WHERE client_id = $1", "mean_ms": 412.0, "calls": 900}],
        missing_idx=["idx_trades_client_status_date"], pool_pending=0, chaos={"apiLatencyMs": 0},
        scan_stats={"seq_scan": 900, "idx_scan": 100})
    assert "MISSING" in cause and "idx_trades_client_status_date" in cause
    assert "412.0 ms" in cause
    assert any("V2__performance_indexes.sql" in a for a in actions)


def test_latency_healthy_db_points_to_app_tier():
    cause, _, actions = analyse_latency([], slow=[{"mean_ms": 2, "calls": 10}], missing_idx=[],
                                        pool_pending=0, chaos=None, scan_stats=None)
    assert "application tier" in cause
    assert any("GC" in a for a in actions)


def test_latency_injection_detected():
    cause, _, _ = analyse_latency([], [], [], 0, {"apiLatencyMs": 800}, None)
    assert "800 ms" in cause


def test_pool_long_running_queries():
    lr = [{"pid": 4242, "seconds": 95.0, "query": "SELECT ... FROM trades"}]
    cause, evidence, actions = analyse_pool(lr, [{"state": "active", "connections": 10}], 1.0, None)
    assert "pid 4242" in cause
    assert any("pg_cancel_backend" in a for a in actions)
    assert "100%" in evidence[0]


def test_pool_without_long_queries_suggests_capacity():
    cause, _, actions = analyse_pool([], [], 0.9, None)
    assert "traffic surge" in cause
    assert any("DB_POOL_SIZE" in a for a in actions)


def test_itil_priority_matrix():
    assert Diagnosis("A", "t", "high", "high", "").priority == "P1"
    assert Diagnosis("A", "t", "medium", "medium", "").priority == "P3"


class FakeCollector:
    """Every source down: diagnosis must still produce a ticket that lists the gaps."""

    def __getattr__(self, name):
        return lambda *a, **k: Result(error=f"{name} unavailable")


def test_diagnose_survives_all_collectors_failing():
    alert = {"labels": {"alertname": "HighApiLatency", "severity": "warning"},
             "annotations": {"summary": "p95 high"}}
    d = diagnose(alert, FakeCollector())
    assert d.priority == "P3"
    assert d.probable_cause
    assert any("slow_queries unavailable" in g for g in d.gaps)

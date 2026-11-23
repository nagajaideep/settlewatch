"""
Evidence gathering. Every collector is best-effort: a failing source becomes a note in the
ticket ("could not reach Prometheus: ...") instead of stopping the incident from being raised.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from .config import Config

log = logging.getLogger(__name__)

EXPECTED_INDEXES = [
    "idx_trades_client_status_date",
    "idx_trades_pending_settle_date",
    "idx_trades_status_updated_at",
    "idx_trades_isin_trade_date",
]


@dataclass
class Result:
    """Value from a collector, or the reason it is missing."""
    value: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    # ---------- Prometheus ----------
    def prom(self, expr: str) -> Result:
        try:
            r = requests.get(f"{self.cfg.prometheus_url}/api/v1/query", params={"query": expr}, timeout=5)
            r.raise_for_status()
            data = r.json()["data"]["result"]
            return Result([(s["metric"], float(s["value"][1])) for s in data])
        except Exception as e:  # noqa: BLE001
            return Result(error=f"Prometheus query failed: {e}")

    def prom_scalar(self, expr: str) -> Result:
        res = self.prom(expr)
        if not res.ok:
            return res
        return Result(res.value[0][1] if res.value else None)

    # ---------- application ----------
    def chaos_status(self) -> Result:
        try:
            r = requests.get(f"{self.cfg.app_url}/api/admin/chaos", timeout=3)
            r.raise_for_status()
            return Result(r.json())
        except Exception as e:  # noqa: BLE001
            return Result(error=f"App unreachable: {e}")

    def recent_log_lines(self, max_lines: int = 25, levels=("ERROR", "WARN")) -> Result:
        path = self.cfg.app_log_file
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                f.seek(max(0, size - 2_000_000))
                lines = f.read().decode("utf-8", "replace").splitlines()
            pattern = re.compile(r"\s(" + "|".join(levels) + r")\s")
            return Result([ln for ln in lines if pattern.search(ln)][-max_lines:])
        except FileNotFoundError:
            return Result(error=f"Log file not found: {path}")
        except Exception as e:  # noqa: BLE001
            return Result(error=f"Could not read logs: {e}")

    # ---------- database ----------
    def _query(self, sql: str, params: tuple = ()) -> Result:
        try:
            import psycopg
            with psycopg.connect(self.cfg.database_url, connect_timeout=5) as conn:
                conn.execute("SET statement_timeout = '10s'")
                cur = conn.execute(sql, params)
                cols = [c.name for c in cur.description]
                return Result([dict(zip(cols, row)) for row in cur.fetchall()])
        except Exception as e:  # noqa: BLE001
            return Result(error=f"Database query failed: {e}")

    def slow_queries(self, limit: int = 5) -> Result:
        return self._query("""
            SELECT left(regexp_replace(query, '\\s+', ' ', 'g'), 160) AS query,
                   calls,
                   round(mean_exec_time::numeric, 2)  AS mean_ms,
                   round(max_exec_time::numeric, 2)   AS max_ms,
                   round(total_exec_time::numeric, 0) AS total_ms,
                   rows
            FROM pg_stat_statements
            WHERE calls >= 3
              AND query NOT ILIKE '%%pg_stat_statements%%'
              AND query NOT ILIKE '%%pg_sleep%%'
            ORDER BY mean_exec_time DESC
            LIMIT %s""", (limit,))

    def long_running_queries(self, min_seconds: int = 5) -> Result:
        return self._query("""
            SELECT pid, usename, application_name, state,
                   round(extract(epoch FROM now() - query_start)::numeric, 1) AS seconds,
                   wait_event_type, left(query, 140) AS query
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
              AND state <> 'idle'
              AND now() - query_start > make_interval(secs => %s)
            ORDER BY query_start
            LIMIT 20""", (min_seconds,))

    def connection_states(self) -> Result:
        return self._query("""
            SELECT coalesce(application_name, '') AS application, state, count(*) AS connections
            FROM pg_stat_activity
            WHERE datname = current_database() AND pid <> pg_backend_pid()
            GROUP BY 1, 2 ORDER BY 3 DESC""")

    def table_scan_stats(self) -> Result:
        return self._query("""
            SELECT relname, seq_scan, seq_tup_read, idx_scan, n_live_tup, n_dead_tup,
                   last_autovacuum, last_autoanalyze
            FROM pg_stat_user_tables WHERE relname = 'trades'""")

    def missing_indexes(self) -> Result:
        res = self._query("SELECT indexname FROM pg_indexes WHERE tablename = 'trades'")
        if not res.ok:
            return res
        present = {r["indexname"] for r in res.value}
        return Result([i for i in EXPECTED_INDEXES if i not in present])

    def failure_breakdown(self, minutes: int = 30) -> Result:
        window = (minutes,)
        by_reason = self._query("""
            SELECT failure_reason AS key, count(*) AS n FROM trades
            WHERE status = 'FAILED' AND updated_at >= now() - make_interval(mins => %s)
            GROUP BY 1 ORDER BY 2 DESC""", window)
        if not by_reason.ok:
            return by_reason
        by_cpty = self._query("""
            SELECT counterparty AS key, count(*) AS n FROM trades
            WHERE status = 'FAILED' AND updated_at >= now() - make_interval(mins => %s)
            GROUP BY 1 ORDER BY 2 DESC LIMIT 5""", window)
        by_isin = self._query("""
            SELECT isin AS key, count(*) AS n FROM trades
            WHERE status = 'FAILED' AND updated_at >= now() - make_interval(mins => %s)
            GROUP BY 1 ORDER BY 2 DESC LIMIT 5""", window)
        settled = self._query("""
            SELECT count(*) AS n FROM trades
            WHERE status = 'SETTLED' AND settled_at >= now() - make_interval(mins => %s)""", window)
        sample = self._query("""
            SELECT trade_ref, client_id, isin, counterparty, failure_reason, updated_at
            FROM trades WHERE status = 'FAILED' AND updated_at >= now() - make_interval(mins => %s)
            ORDER BY updated_at DESC LIMIT 5""", window)
        return Result({
            "minutes": minutes,
            "by_reason": by_reason.value,
            "by_counterparty": by_cpty.value or [],
            "by_isin": by_isin.value or [],
            "settled": (settled.value or [{"n": 0}])[0]["n"],
            "sample": sample.value or [],
        })

#!/usr/bin/env python3
"""
Before/after index benchmark for SettleWatch's hot queries.

1. drops the V2 performance indexes and ANALYZEs
2. runs every query in queries.sql with EXPLAIN (ANALYZE, BUFFERS): 1 warm-up + N timed runs
3. recreates the indexes from the Flyway migration and ANALYZEs
4. runs the same queries again
5. writes perf/results/RESULTS.md plus the full plans for each query

Only needs `psql` on PATH. Connection comes from the standard PG* env vars, e.g.
    PGHOST=localhost PGUSER=settlewatch PGPASSWORD=settlewatch PGDATABASE=settlewatch python3 perf/benchmark.py
"""
import json
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MIGRATION = ROOT / "src/main/resources/db/migration/V2__performance_indexes.sql"
RESULTS = HERE / "results"
RUNS = int(os.environ.get("BENCH_RUNS", "5"))


def psql(sql: str) -> str:
    out = subprocess.run(["psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"psql failed: {out.stderr.strip()}\nSQL: {sql[:200]}")
    return out.stdout.strip()


def load_queries() -> list[tuple[str, str]]:
    text = (HERE / "queries.sql").read_text()
    blocks = re.split(r"^-- name: (.+)$", text, flags=re.M)[1:]
    return [(blocks[i].strip(), blocks[i + 1].strip().rstrip(";")) for i in range(0, len(blocks), 2)]


def index_names() -> list[str]:
    return re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)", MIGRATION.read_text())


def explain(sql: str) -> dict:
    raw = psql(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
    return json.loads(raw)[0]


def explain_text(sql: str) -> str:
    return psql(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")


def top_node(plan: dict) -> str:
    """Describe the scan strategy, e.g. 'Index Scan using idx_x' or 'Parallel Seq Scan'."""
    found = []

    def walk(node):
        nt = ("Parallel " if node.get("Parallel Aware") else "") + node["Node Type"]
        if "Scan" in nt:
            found.append(f"{nt} using {node['Index Name']}" if "Index Name" in node else nt)
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return ", ".join(dict.fromkeys(found)) or plan["Plan"]["Node Type"]


def measure(queries, label):
    results = {}
    for name, sql in queries:
        explain(sql)  # warm-up: populate shared buffers / OS cache
        times, plan = [], None
        for _ in range(RUNS):
            plan = explain(sql)
            times.append(plan["Execution Time"])
        buffers = plan["Plan"].get("Shared Hit Blocks", 0) + plan["Plan"].get("Shared Read Blocks", 0)
        results[name] = {"median_ms": statistics.median(times), "min_ms": min(times),
                         "strategy": top_node(plan), "buffers": buffers}
        slug = name.split()[0].lower()
        (RESULTS / f"{slug}_{label}.txt").write_text(f"-- {name}\n{sql};\n\n{explain_text(sql)}\n")
        print(f"  [{label}] {name}: median {results[name]['median_ms']:.2f} ms  ({results[name]['strategy']})")
    return results


def fmt(ms: float) -> str:
    return f"{ms / 1000:.2f} s" if ms >= 1000 else (f"{ms:.1f} ms" if ms >= 1 else f"{ms:.3f} ms")


def main():
    RESULTS.mkdir(exist_ok=True)
    queries = load_queries()
    rows = int(psql("SELECT count(*) FROM trades"))
    table_size = psql("SELECT pg_size_pretty(pg_table_size('trades'))")
    pg_version = psql("SHOW server_version")
    print(f"trades: {rows:,} rows ({table_size}), PostgreSQL {pg_version}, {RUNS} timed runs per query")

    print("Dropping performance indexes...")
    for idx in index_names():
        psql(f"DROP INDEX IF EXISTS {idx}")
    psql("ANALYZE trades")
    before = measure(queries, "before")

    print("Creating performance indexes...")
    psql(MIGRATION.read_text())
    psql("ANALYZE trades")
    index_sizes = psql("""SELECT string_agg(indexrelname || '=' || pg_size_pretty(pg_relation_size(indexrelid)), ', ')
                          FROM pg_stat_user_indexes WHERE relname = 'trades'""")
    after = measure(queries, "after")

    lines = [
        "# Query performance: before vs after indexing",
        "",
        f"- Dataset: **{rows:,} trades** ({table_size} heap), PostgreSQL {pg_version}",
        f"- Method: `EXPLAIN (ANALYZE, BUFFERS)`, 1 warm-up + median of {RUNS} runs, warm cache",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `perf/benchmark.py`",
        "",
        "| Query | Before | After | Speed-up | Buffers before → after | Plan before | Plan after |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for name, _ in queries:
        b, a = before[name], after[name]
        speedup = b["median_ms"] / a["median_ms"] if a["median_ms"] else float("inf")
        lines.append(f"| {name} | {fmt(b['median_ms'])} | {fmt(a['median_ms'])} | **{speedup:,.0f}x** "
                     f"| {b['buffers']:,} → {a['buffers']:,} | {b['strategy']} | {a['strategy']} |")
    lines += ["", f"Index sizes: {index_sizes}", "",
              "Full plans for each query are in this folder (`q*_before.txt`, `q*_after.txt`)."]
    (RESULTS / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

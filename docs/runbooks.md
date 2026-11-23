# Runbooks

Every Prometheus alert links here, and every ticket the SRE bot raises links to the matching section.
The bot already runs the diagnostic steps marked 🤖 and attaches the output to the ticket. The rest
are for the on-call engineer.

Severity → ITIL priority: `critical` = impact high, urgency high → **P1**; `warning` = medium/medium → **P3**.

---

## SettlementFailureSpike

**Fires when** more than 10% of settlement attempts failed over 10 minutes (with at least 20 attempts),
sustained for 2 minutes. The normal baseline is about 3%.

**Business impact:** failed settlements leave clients without securities or cash on the intended date.
They can incur CSDR penalties and need client communication before the market cut-off.

1. 🤖 Break fails down by reason, counterparty and ISIN for the last 30 minutes.
2. 🤖 Check whether fault injection is active (`GET /api/admin/chaos`). If it is, the ticket is marked `[DRILL]`.
3. If one reason dominates, follow the reason-specific step the bot suggests (for example, `SSI_MISMATCH` means
   comparing standing settlement instructions after a static-data change).
4. If one counterparty dominates, contact their operations desk and consider holding new trades with them.
5. Once the cause is fixed, re-queue: `POST /api/trades/{ref}/retry`.
6. Close the ticket with the root cause and the number of affected trades and clients.

## HighApiLatency

**Fires when** the p95 latency of `/api/**` (admin excluded) is above 500 ms for 2 minutes.

1. 🤖 Collect p95 per endpoint from Prometheus.
2. 🤖 Collect the top statements by mean time from `pg_stat_statements`.
3. 🤖 Check that the performance indexes from `V2__performance_indexes.sql` exist. A dropped index turns
   a 0.2 ms query into a full scan of a million rows (see [performance.md](performance.md)).
4. 🤖 Collect the seq-scan vs index-scan ratio on `trades`, and the connection-pool wait.
5. If the DB is clean, look at the app tier: GC panel, heap, CPU, thread dump (`jcmd <pid> Thread.print`).

## DbConnectionPoolSaturated

**Fires when** Hikari active/max is above 80%, or any thread is waiting for a connection, for 1 minute.

1. 🤖 List queries running for 5 seconds or more (`pg_stat_activity`) and session counts by state.
2. Find the caller of the long-running statements. Cancel with `SELECT pg_cancel_backend(<pid>)`, and use
   `pg_terminate_backend` only if cancel fails.
3. With no long queries, it's load: compare request rate against baseline and consider raising `DB_POOL_SIZE`
   (keep pool size × instances below Postgres `max_connections`).
4. Follow-up: set a `statement_timeout` on the application role.

## SettlementBacklogGrowing

**Fires when** more than 5,000 due trades have been waiting to settle for 10 minutes.

1. 🤖 Report the backlog size and sweep duration.
2. Check the logs for `Settlement sweep failed`.
3. Drain manually: `POST /api/settlements/sweep`.
4. Scale: raise `SETTLEMENT_BATCH_SIZE`, or run more instances. `FOR UPDATE SKIP LOCKED` makes concurrent
   sweeps safe.

## ApiErrorRateHigh

**Fires when** more than 5% of API calls return 5xx for 2 minutes.

1. 🤖 Attach recent `ERROR` log lines.
2. Correlate with deploys (GitHub Actions history) and DB health. Roll back with the deploy workflow,
   using the previous image SHA.

## SettleWatchDown

**Fires when** Prometheus can't scrape `/actuator/prometheus` for 1 minute.

1. `docker compose ps app` and `docker compose logs --tail=200 app`.
2. Common causes: OOM (`ExitOnOutOfMemoryError` is set, so the container restarts), a failed Flyway
   migration, or the DB being unreachable at startup.
3. Restart with `docker compose restart app`, or redeploy the last known-good tag.

---

## Rehearsing incidents (game day)

```bash
# Settlement failure spike (fires SettlementFailureSpike after ~2-3 min with loadgen running)
curl -XPOST 'localhost:8080/api/admin/chaos/failure-rate?rate=0.5'

# Slow API (fires HighApiLatency)
curl -XPOST 'localhost:8080/api/admin/chaos/latency?ms=800'

# Pool exhaustion: hold 9 of 10 connections for 3 minutes (fires DbConnectionPoolSaturated)
curl -XPOST 'localhost:8080/api/admin/chaos/hog-connections?connections=9&seconds=180'

# Real performance regression: drop an index and watch the bot name it as the cause
docker compose exec postgres psql -U settlewatch -c 'DROP INDEX idx_trades_client_status_date'

# Clear everything
curl -XPOST localhost:8080/api/admin/chaos/reset
```

Tickets: `http://localhost:8000/tickets` (dry-run mode) or your Jira project.

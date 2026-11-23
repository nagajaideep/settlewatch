"""Alertmanager webhook receiver."""
from __future__ import annotations

import logging
import threading
from collections import deque

from pathlib import Path

from flask import Flask, Response, abort, jsonify, request

from .collectors import Collector
from .config import Config
from .diagnosis import diagnose, now_iso
from .tickets import Ticketer, incident_label, make_ticketer, ticket_summary

log = logging.getLogger(__name__)


def create_app(cfg: Config | None = None, collector: Collector | None = None,
               ticketer: Ticketer | None = None) -> Flask:
    cfg = cfg or Config.from_env()
    collector = collector or Collector(cfg)
    ticketer = ticketer or make_ticketer(cfg)
    history: deque = deque(maxlen=200)
    lock = threading.Lock()  # Alertmanager may retry concurrently; avoid duplicate tickets

    app = Flask(__name__)

    def handle(alert: dict) -> dict:
        name = alert.get("labels", {}).get("alertname", "UnknownAlert")
        label = incident_label(alert)
        status = alert.get("status", "firing")
        with lock:
            existing = ticketer.find_open(label)
            if status == "resolved":
                if existing:
                    ticketer.comment(existing, f"Alert {name} resolved at {alert.get('endsAt', now_iso())}. "
                                               "Monitoring shows recovery; confirm root cause and close.")
                    return {"alert": name, "action": "commented-resolved", "ticket": existing.key}
                return {"alert": name, "action": "ignored-resolved-no-ticket"}
            if existing:
                ticketer.comment(existing, f"Alert {name} is still firing as of {now_iso()}.")
                return {"alert": name, "action": "commented-still-firing", "ticket": existing.key}
            diagnosis = diagnose(alert, collector)
            labels = ["settlewatch", "auto-incident", name, label]
            ticket = ticketer.create(ticket_summary(diagnosis), diagnosis, alert, labels)
            log.warning("Incident %s raised for %s (%s): %s", ticket.key, name, diagnosis.priority,
                        diagnosis.probable_cause[:200])
            return {"alert": name, "action": "created", "ticket": ticket.key, "url": ticket.url,
                    "priority": diagnosis.priority, "probable_cause": diagnosis.probable_cause}

    @app.post("/alerts")
    def alerts():
        payload = request.get_json(force=True, silent=True) or {}
        results = []
        for alert in payload.get("alerts", []):
            try:
                results.append(handle(alert))
            except Exception as e:  # noqa: BLE001 - one bad alert must not drop the others
                log.exception("Failed to handle alert")
                results.append({"alert": alert.get("labels", {}).get("alertname"), "action": "error",
                                "error": str(e)})
        for r in results:
            history.appendleft({"at": now_iso(), **r})
        return jsonify({"results": results})

    @app.get("/incidents")
    def incidents():
        return jsonify(list(history))

    @app.get("/tickets")
    def tickets():
        """Dry-run mode only: list the Markdown tickets written so far."""
        if cfg.jira_enabled:
            return jsonify({"jira": cfg.jira_base_url})
        files = sorted(Path(cfg.tickets_dir).glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return jsonify([f.stem for f in files])

    @app.get("/tickets/<key>")
    def ticket(key: str):
        path = Path(cfg.tickets_dir) / f"{key}.md"
        if cfg.jira_enabled or not key.replace("-", "").isalnum() or not path.exists():
            abort(404)
        return Response(path.read_text(), mimetype="text/markdown")

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok", "jira": cfg.jira_enabled})

    return app

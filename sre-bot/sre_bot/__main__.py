"""
python -m sre_bot serve                     # run the webhook server on :8000
python -m sre_bot diagnose HighApiLatency   # one-off diagnosis printed as Markdown (no ticket)
python -m sre_bot raise HighApiLatency      # diagnose and raise a ticket, as if the alert fired
"""
import argparse
import logging
import uuid

from .collectors import Collector
from .config import Config
from .diagnosis import diagnose, now_iso
from .tickets import incident_label, make_ticketer, render_markdown, ticket_summary

SEVERITY = {"SettlementFailureSpike": "critical", "DbConnectionPoolSaturated": "critical",
            "SettleWatchDown": "critical"}


def synthetic_alert(name: str) -> dict:
    return {"status": "firing", "fingerprint": uuid.uuid4().hex[:16], "startsAt": now_iso(),
            "labels": {"alertname": name, "severity": SEVERITY.get(name, "warning"), "service": "settlewatch"},
            "annotations": {"summary": f"{name} (manually triggered)",
                            "runbook": f"docs/runbooks.md#{name.lower()}"}}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    p = argparse.ArgumentParser(prog="sre_bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    for cmd in ("diagnose", "raise"):
        sub.add_parser(cmd).add_argument("alertname")
    args = p.parse_args()

    cfg = Config.from_env()
    if args.cmd == "serve":
        from .app import create_app
        create_app(cfg).run(host="0.0.0.0", port=args.port)
        return
    alert = synthetic_alert(args.alertname)
    d = diagnose(alert, Collector(cfg))
    if args.cmd == "diagnose":
        print(render_markdown(d, alert, cfg))
    else:
        t = make_ticketer(cfg).create(ticket_summary(d), d, alert,
                                      ["settlewatch", "auto-incident", args.alertname, incident_label(alert)])
        print(f"{t.key}: {t.url}")


if __name__ == "__main__":
    main()

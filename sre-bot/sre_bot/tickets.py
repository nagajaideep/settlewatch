"""
Ticket rendering and delivery. Two backends share one interface:
  JiraTicketer   - Jira Cloud REST API v3 (works on the free plan)
  DryRunTicketer - writes Markdown files, used when no Jira credentials are configured
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from .config import Config
from .diagnosis import Diagnosis, now_iso

log = logging.getLogger(__name__)


@dataclass
class Ticket:
    key: str
    url: str


class Ticketer(Protocol):
    def find_open(self, label: str) -> Ticket | None: ...
    def create(self, summary: str, diagnosis: Diagnosis, alert: dict, labels: list[str]) -> Ticket: ...
    def comment(self, ticket: Ticket, text: str) -> None: ...


def incident_label(alert: dict) -> str:
    fp = alert.get("fingerprint") or re.sub(r"\W", "", json.dumps(alert.get("labels", {}), sort_keys=True))[:16]
    return f"settlewatch-{fp[:16]}"


def ticket_summary(d: Diagnosis) -> str:
    drill = "[DRILL] " if d.fault_injection_active else ""
    return f"{drill}[{d.priority}] {d.alertname}: {d.title}"[:250]


def _fields(d: Diagnosis, alert: dict, cfg: Config) -> list[tuple[str, str]]:
    labels = alert.get("labels", {})
    runbook = alert.get("annotations", {}).get("runbook", "docs/runbooks.md")
    return [
        ("Priority (ITIL)", f"{d.priority} (impact {d.impact}, urgency {d.urgency})"),
        ("Service", labels.get("service", "settlewatch")),
        ("Category", "Incident / " + labels.get("service", "application")),
        ("Detected", alert.get("startsAt", now_iso())),
        ("Detection source", "Prometheus alert → Alertmanager → SettleWatch SRE bot"),
        ("Runbook", cfg.runbook_base_url + runbook),
        ("Dashboard", f"{cfg.grafana_url}/d/settlewatch-main"),
    ]


def _cell(v: Any) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def render_markdown(d: Diagnosis, alert: dict, cfg: Config) -> str:
    out = [f"# {ticket_summary(d)}", ""]
    out += [f"- **{k}:** {v}" for k, v in _fields(d, alert, cfg)]
    desc = alert.get("annotations", {}).get("description")
    if desc:
        out += ["", f"> {desc}"]
    out += ["", "## Probable cause", d.probable_cause or "Unknown", "", "## Evidence"]
    out += [f"- {e}" for e in d.evidence] or ["- none collected"]
    out += ["", "## Recommended actions"] + [f"{i}. {a}" for i, a in enumerate(d.actions, 1)]
    for title, rows in d.tables.items():
        out += ["", f"## {title}"]
        if not rows:
            out.append("_none_")
            continue
        cols = list(rows[0].keys())
        out += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        out += ["| " + " | ".join(_cell(r.get(c)) for c in cols) + " |" for r in rows]
    out += ["", "## Recent WARN/ERROR log lines", "```"] + (d.logs[-10:] or ["(none)"]) + ["```"]
    if d.gaps:
        out += ["", "## Data gaps"] + [f"- {g}" for g in d.gaps]
    out += ["", f"_Raised automatically by SettleWatch SRE bot at {now_iso()}._"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- Atlassian Document Format

def _text(t: str, bold=False) -> dict:
    node = {"type": "text", "text": t}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return node


def _para(*parts) -> dict:
    return {"type": "paragraph", "content": [p if isinstance(p, dict) else _text(p) for p in parts if p]}


def _heading(t: str) -> dict:
    return {"type": "heading", "attrs": {"level": 3}, "content": [_text(t)]}


def _list(items: list[str], ordered=False) -> dict:
    return {"type": "orderedList" if ordered else "bulletList",
            "content": [{"type": "listItem", "content": [_para(i)]} for i in items]}


def _code(lines: list[str]) -> dict:
    return {"type": "codeBlock", "attrs": {}, "content": [_text("\n".join(lines) or "(none)")]}


def _table(rows: list[dict]) -> dict:
    cols = list(rows[0].keys())
    header = {"type": "tableRow", "content": [
        {"type": "tableHeader", "content": [_para(c)]} for c in cols]}
    body = [{"type": "tableRow", "content": [
        {"type": "tableCell", "content": [_para(str(r.get(c, "")) or "-")]} for c in cols]} for r in rows]
    return {"type": "table", "content": [header] + body}


def render_adf(d: Diagnosis, alert: dict, cfg: Config) -> dict:
    content = [_list([f"{k}: {v}" for k, v in _fields(d, alert, cfg)])]
    desc = alert.get("annotations", {}).get("description")
    if desc:
        content.append(_para(desc))
    content += [_heading("Probable cause"), _para(d.probable_cause or "Unknown"),
                _heading("Evidence"), _list(d.evidence or ["none collected"]),
                _heading("Recommended actions"), _list(d.actions or ["Investigate"], ordered=True)]
    for title, rows in d.tables.items():
        content.append(_heading(title))
        content.append(_table(rows) if rows else _para("none"))
    content += [_heading("Recent WARN/ERROR log lines"), _code(d.logs[-10:])]
    if d.gaps:
        content += [_heading("Data gaps"), _list(d.gaps)]
    content.append(_para(_text(f"Raised automatically by SettleWatch SRE bot at {now_iso()}.")))
    return {"type": "doc", "version": 1, "content": content}


# ---------------------------------------------------------------- backends

class JiraTicketer:
    def __init__(self, cfg: Config, session: requests.Session | None = None):
        self.cfg = cfg
        self.http = session or requests.Session()
        self.http.auth = (cfg.jira_email, cfg.jira_api_token)
        self.http.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self.cfg.jira_base_url}/rest/api/3/{path}"

    def _browse(self, key: str) -> str:
        return f"{self.cfg.jira_base_url}/browse/{key}"

    def find_open(self, label: str) -> Ticket | None:
        jql = (f'project = "{self.cfg.jira_project_key}" AND labels = "{label}" '
               f'AND statusCategory != Done ORDER BY created DESC')
        r = self.http.get(self._url("search/jql"), params={"jql": jql, "maxResults": 1, "fields": "key"},
                          timeout=10)
        r.raise_for_status()
        issues = r.json().get("issues", [])
        return Ticket(issues[0]["key"], self._browse(issues[0]["key"])) if issues else None

    def create(self, summary: str, diagnosis: Diagnosis, alert: dict, labels: list[str]) -> Ticket:
        payload = {"fields": {
            "project": {"key": self.cfg.jira_project_key},
            "issuetype": {"name": self.cfg.jira_issue_type},
            "summary": summary,
            "labels": labels,
            "description": render_adf(diagnosis, alert, self.cfg),
        }}
        r = self.http.post(self._url("issue"), data=json.dumps(payload), timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f"Jira create failed ({r.status_code}): {r.text[:500]}")
        key = r.json()["key"]
        log.info("Created Jira issue %s", key)
        return Ticket(key, self._browse(key))

    def comment(self, ticket: Ticket, text: str) -> None:
        body = {"body": {"type": "doc", "version": 1, "content": [_para(text)]}}
        r = self.http.post(self._url(f"issue/{ticket.key}/comment"), data=json.dumps(body), timeout=10)
        r.raise_for_status()


class DryRunTicketer:
    """Writes tickets as Markdown so the whole flow works without a Jira account."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dir = Path(cfg.tickets_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.dir / "index.json"

    def _index(self) -> dict:
        try:
            return json.loads(self.index_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"next": 1, "open": {}}

    def _save(self, idx: dict) -> None:
        self.index_file.write_text(json.dumps(idx, indent=2))

    def find_open(self, label: str) -> Ticket | None:
        key = self._index()["open"].get(label)
        return Ticket(key, str(self.dir / f"{key}.md")) if key else None

    def create(self, summary: str, diagnosis: Diagnosis, alert: dict, labels: list[str]) -> Ticket:
        idx = self._index()
        key = f"{self.cfg.jira_project_key}-{idx['next']}"
        idx["next"] += 1
        for label in labels:
            if label.startswith("settlewatch-"):
                idx["open"][label] = key
        self._save(idx)
        path = self.dir / f"{key}.md"
        path.write_text(f"<!-- labels: {', '.join(labels)} -->\n" + render_markdown(diagnosis, alert, self.cfg))
        log.info("DRY RUN: wrote ticket %s", path)
        return Ticket(key, str(path))

    def comment(self, ticket: Ticket, text: str) -> None:
        with open(self.dir / f"{ticket.key}.md", "a") as f:
            f.write(f"\n---\n**Comment ({now_iso()}):** {text}\n")
        if "resolved" in text.lower():
            idx = self._index()
            idx["open"] = {k: v for k, v in idx["open"].items() if v != ticket.key}
            self._save(idx)


def make_ticketer(cfg: Config) -> Ticketer:
    return JiraTicketer(cfg) if cfg.jira_enabled else DryRunTicketer(cfg)

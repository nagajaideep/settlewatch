import json

import responses

from sre_bot.app import create_app
from sre_bot.collectors import Result
from sre_bot.config import Config
from sre_bot.tickets import JiraTicketer, render_adf
from sre_bot.diagnosis import Diagnosis


class StubCollector:
    def __getattr__(self, name):
        return lambda *a, **k: Result(error="offline")

    def failure_breakdown(self, minutes):
        return Result({"minutes": minutes, "settled": 100, "sample": [],
                       "by_reason": [{"key": "SSI_MISMATCH", "n": 60}],
                       "by_counterparty": [], "by_isin": []})


def alert(status="firing", fp="abc123"):
    return {"status": status, "fingerprint": fp, "startsAt": "2026-11-23T10:00:00Z",
            "labels": {"alertname": "SettlementFailureSpike", "severity": "critical", "service": "settlement-engine"},
            "annotations": {"summary": "Fail rate above 10%", "runbook": "docs/runbooks.md#x"}}


def client(tmp_path):
    cfg = Config(tickets_dir=str(tmp_path))
    return create_app(cfg, collector=StubCollector()).test_client()


def test_firing_alert_creates_one_ticket_then_dedupes(tmp_path):
    c = client(tmp_path)
    first = c.post("/alerts", json={"alerts": [alert()]}).get_json()["results"][0]
    assert first["action"] == "created" and first["ticket"] == "OPS-1" and first["priority"] == "P1"
    body = (tmp_path / "OPS-1.md").read_text()
    assert "SSI_MISMATCH" in body and "Probable cause" in body and "offline" in body

    again = c.post("/alerts", json={"alerts": [alert()]}).get_json()["results"][0]
    assert again == {"alert": "SettlementFailureSpike", "action": "commented-still-firing", "ticket": "OPS-1"}


def test_resolved_alert_comments_and_closes(tmp_path):
    c = client(tmp_path)
    c.post("/alerts", json={"alerts": [alert()]})
    res = c.post("/alerts", json={"alerts": [alert("resolved")]}).get_json()["results"][0]
    assert res["action"] == "commented-resolved"
    assert "resolved" in (tmp_path / "OPS-1.md").read_text()
    # a new firing after resolution opens a fresh incident
    assert c.post("/alerts", json={"alerts": [alert()]}).get_json()["results"][0]["ticket"] == "OPS-2"


def test_ticket_endpoints(tmp_path):
    c = client(tmp_path)
    c.post("/alerts", json={"alerts": [alert()]})
    assert c.get("/tickets").get_json() == ["OPS-1"]
    assert b"Probable cause" in c.get("/tickets/OPS-1").data
    assert c.get("/tickets/../etc").status_code == 404


@responses.activate
def test_jira_backend_searches_then_creates():
    cfg = Config(jira_base_url="https://example.atlassian.net", jira_email="bot@example.com",
                 jira_api_token="t", jira_project_key="OPS")
    responses.get("https://example.atlassian.net/rest/api/3/search/jql", json={"issues": []})
    responses.post("https://example.atlassian.net/rest/api/3/issue", json={"key": "OPS-77"})

    app = create_app(cfg, collector=StubCollector(), ticketer=JiraTicketer(cfg))
    res = app.test_client().post("/alerts", json={"alerts": [alert()]}).get_json()["results"][0]

    assert res["ticket"] == "OPS-77"
    assert res["url"] == "https://example.atlassian.net/browse/OPS-77"
    sent = json.loads(responses.calls[1].request.body)["fields"]
    assert sent["project"] == {"key": "OPS"}
    assert sent["summary"].startswith("[P1] SettlementFailureSpike")
    assert "settlewatch-abc123" in sent["labels"]
    assert sent["description"]["type"] == "doc"
    assert "labels = \"settlewatch-abc123\"" in responses.calls[0].request.params["jql"]


def test_adf_tables_render():
    d = Diagnosis("X", "t", "high", "high", "cause", tables={"T": [{"a": 1, "b": None}]})
    doc = render_adf(d, {"labels": {}}, Config())
    table = next(n for n in doc["content"] if n["type"] == "table")
    assert len(table["content"]) == 2

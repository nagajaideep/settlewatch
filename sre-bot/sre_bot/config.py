import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    prometheus_url: str = "http://localhost:9090"
    app_url: str = "http://localhost:8080"
    database_url: str = "postgresql://settlewatch:settlewatch@localhost:5432/settlewatch"
    app_log_file: str = "../logs/settlewatch.log"
    grafana_url: str = "http://localhost:3000"
    runbook_base_url: str = "https://github.com/nagajaideep/settlewatch/blob/main/"
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = field(default="", repr=False)
    jira_project_key: str = "OPS"
    jira_issue_type: str = "Task"
    tickets_dir: str = "tickets"

    @property
    def jira_enabled(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @classmethod
    def from_env(cls) -> "Config":
        d = cls()
        get = lambda name, default: os.environ.get(name) or default  # noqa: E731 - empty string means unset
        return cls(
            prometheus_url=get("PROMETHEUS_URL", d.prometheus_url),
            app_url=get("APP_URL", d.app_url),
            database_url=get("DATABASE_URL", d.database_url),
            app_log_file=get("APP_LOG_FILE", d.app_log_file),
            grafana_url=get("GRAFANA_URL", d.grafana_url),
            runbook_base_url=get("RUNBOOK_BASE_URL", d.runbook_base_url),
            jira_base_url=get("JIRA_BASE_URL", "").rstrip("/"),
            jira_email=get("JIRA_EMAIL", ""),
            jira_api_token=get("JIRA_API_TOKEN", ""),
            jira_project_key=get("JIRA_PROJECT_KEY", d.jira_project_key),
            jira_issue_type=get("JIRA_ISSUE_TYPE", d.jira_issue_type),
            tickets_dir=get("TICKETS_DIR", "/data/tickets" if os.path.isdir("/data") else d.tickets_dir),
        )

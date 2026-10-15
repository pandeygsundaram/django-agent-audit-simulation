import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

ISSUES_DIR = Path(__file__).resolve().parent.parent / "issues"
ISSUES_DIR.mkdir(exist_ok=True)

class IssueTracker:
    """
    Manages error issues, human feedback status, and pull request tracking.
    """

    @staticmethod
    def create_issue(event_data: Dict[str, Any], initial_audit: Dict[str, Any], thread_ts: str) -> Dict[str, Any]:
        timestamp = int(time.time())
        issue_id = f"ISSUE-{timestamp % 100000}"
        
        issue_data = {
            "issue_id": issue_id,
            "status": "OPEN",  # OPEN -> APPROVED -> FIXING -> PR_RAISED -> CLOSED
            "created_at": timestamp,
            "thread_ts": thread_ts,
            "error_type": event_data.get("error_type", "BackendError"),
            "error_message": event_data.get("error_message", ""),
            "source": event_data.get("source", "Backend"),
            "request": event_data.get("request", {}),
            "traceback": event_data.get("traceback", ""),
            "proposed_fix": initial_audit,
            "human_feedback": None,
            "pr_details": None
        }

        file_path = ISSUES_DIR / f"{issue_id}.json"
        file_path.write_text(json.dumps(issue_data, indent=2), encoding="utf-8")
        return issue_data

    @staticmethod
    def get_issue(issue_id: str) -> Optional[Dict[str, Any]]:
        file_path = ISSUES_DIR / f"{issue_id}.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text(encoding="utf-8"))

    @staticmethod
    def update_issue(issue_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        file_path = ISSUES_DIR / f"{issue_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        data.update(updates)
        file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    @staticmethod
    def list_open_issues() -> List[Dict[str, Any]]:
        issues = []
        for p in ISSUES_DIR.glob("ISSUE-*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("status") in ["OPEN", "APPROVED"]:
                issues.append(data)
        return sorted(issues, key=lambda x: x.get("created_at", 0), reverse=True)

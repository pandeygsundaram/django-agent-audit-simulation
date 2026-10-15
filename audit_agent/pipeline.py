import logging
from typing import Dict, Any
from .slack_client import SlackAuditorNotifier
from .context_extractor import build_agent_context
from .agent import AuditorAgent
from .issue_tracker import IssueTracker

logger = logging.getLogger(__name__)

# Singletons
notifier = SlackAuditorNotifier()
agent = AuditorAgent()

def run_audit_pipeline(event_data: Dict[str, Any]):
    """
    Executes the audit lifecycle:
    1. Send initial alert to Slack channel.
    2. Extract code context and traceback frames.
    3. Run AI agent to propose root cause and code patch.
    4. Register issue in IssueTracker.
    5. Post proposed fix to Slack thread with human review instructions.
    """
    error_type = event_data.get("error_type", "BackendError")
    logger.info(f"[Pipeline] Processing error event: {error_type}")

    # Step 1: Fire message on Slack channel
    thread_ts = notifier.post_initial_alert(event_data)

    # Step 2: Extract code context & frames from repository
    enriched_context = build_agent_context(event_data)

    # Step 3: Spawn Agent to audit root cause and propose fix
    audit_report = agent.audit(enriched_context)

    # Step 4: Create Issue locally and on GitHub
    from .github_client import GitHubClient
    gh_client = GitHubClient()
    gh_issue = None

    if gh_client.is_configured:
        req = event_data.get("request", {})
        issue_body = (
            f"### Automated Exception Report\n\n"
            f"- **Error Type:** `{error_type}`\n"
            f"- **Message:** `{event_data.get('error_message')}`\n"
            f"- **Endpoint:** `{req.get('method')} {req.get('path')}`\n"
            f"- **Source:** `{event_data.get('source')}`\n\n"
            f"### AI Diagnosis\n"
            f"{audit_report.get('root_cause')}\n\n"
            f"### Proposed Fix\n"
            f"```python\n{audit_report.get('suggested_fix')}\n```\n\n"
            f"### Traceback\n"
            f"```\n{event_data.get('traceback', '')[:1000]}\n```"
        )
        gh_issue = gh_client.create_issue(
            title=f"[Bug]: {error_type} in {req.get('method', 'N/A')} {req.get('path', 'N/A')}",
            body=issue_body
        )

    issue = IssueTracker.create_issue(event_data, audit_report, thread_ts)
    issue_id = issue["issue_id"]

    if gh_issue:
        IssueTracker.update_issue(issue_id, {
            "github_issue_number": gh_issue.get("issue_number"),
            "github_issue_url": gh_issue.get("issue_url")
        })

    # Append Issue ID, GitHub URL, and Human review instructions
    gh_link_text = f"\n*GitHub Issue:* {gh_issue.get('issue_url')}" if gh_issue else ""
    audit_report["summary"] = f"[{issue_id}] " + audit_report.get("summary", "")
    audit_report["root_cause"] += (
        f"{gh_link_text}\n\n"
        f"*Review Status:* Waiting for human feedback on `{issue_id}`.\n"
        f"To approve and launch Kubernetes sandbox, run:\n"
        f"`python review_cli.py {issue_id} \"Approved, please proceed\"`"
    )

    # Step 5: Reply in the Slack thread
    notifier.post_audit_report(thread_ts, audit_report)

    logger.info(f"[Pipeline] Audit complete for {error_type}. Issue {issue_id} logged to thread {thread_ts}")
    return audit_report

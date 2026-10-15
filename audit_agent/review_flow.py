import logging
import json
from typing import Dict, Any, Optional
from pathlib import Path
from .issue_tracker import IssueTracker
from .k8s_sandbox import KubernetesSandboxRunner
from .slack_client import SlackAuditorNotifier
import config

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

def process_human_review(issue_id: str, human_feedback: str) -> Dict[str, Any]:
    """
    Takes an issue ID and human feedback, queries Groq to generate the updated file
    incorporating the feedback, executes validation in an isolated Kubernetes Pod,
    and generates a Pull Request against codebase-qa.
    """
    issue = IssueTracker.get_issue(issue_id)
    if not issue:
        return {"success": False, "error": f"Issue not found: {issue_id}"}

    logger.info(f"Processing human review for {issue_id}: '{human_feedback}'")
    thread_ts = issue.get("thread_ts")
    notifier = SlackAuditorNotifier()

    # Determine target file
    proposed_audit = issue.get("proposed_fix", {})
    target_location = proposed_audit.get("affected_location", "")
    rel_path = "demo_app/views.py"
    if ":" in target_location:
        rel_path = target_location.split(":")[0].replace(str(REPO_ROOT) + "/", "")

    target_file_path = REPO_ROOT / rel_path
    if not target_file_path.exists():
        return {"success": False, "error": f"File not found on host: {rel_path}"}

    original_file_content = target_file_path.read_text(encoding="utf-8")

    # Generate updated file using Groq LLM
    updated_file_content = ""
    summary = proposed_audit.get("summary", "Automated bug repair")

    if config.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            prompt = f"""You are an expert Python and Django backend engineer.
You are tasked with fixing a bug in {rel_path}.

ERROR DETAILS:
Error: {issue.get('error_type')}: {issue.get('error_message')}
Endpoint: {issue.get('request', {}).get('method')} {issue.get('request', {}).get('path')}
Traceback:
{issue.get('traceback')}

INITIAL PROPOSAL:
{proposed_audit.get('suggested_fix')}

HUMAN REVIEWER FEEDBACK:
"{human_feedback}"

CURRENT FILE CONTENT ({rel_path}):
```python
{original_file_content}
```

Instructions:
1. Fix the bug while incorporating the human reviewer feedback.
2. Return the COMPLETE, VALID Python code for {rel_path}.
3. Do not omit any functions or imports.

Return your response strictly as JSON with this schema:
{{
  "updated_file_content": "<complete python code of the file>",
  "summary": "<1-line summary of what was fixed>"
}}
"""
            completion = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            res_data = json.loads(completion.choices[0].message.content)
            updated_file_content = res_data.get("updated_file_content", "")
            summary = res_data.get("summary", summary)
        except Exception as e:
            logger.error(f"Groq code generation failed: {e}")

    # Fallback if LLM failed
    if not updated_file_content:
        # Heuristic simple fix
        suggested = proposed_audit.get("suggested_fix", "")
        updated_file_content = original_file_content.replace(
            'payment_method = data["payment_method"]',
            'payment_method = data.get("payment_method")\n    if not payment_method:\n        return JsonResponse({"error": "payment_method is required"}, status=400)'
        )

    # Launch isolated Kubernetes Pod sandbox
    k8s_runner = KubernetesSandboxRunner(repo_root=str(REPO_ROOT))
    k8s_result = k8s_runner.run_k8s_repair(
        issue_id=issue_id,
        relative_file_path=rel_path,
        updated_file_content=updated_file_content,
        summary=summary,
        human_feedback=human_feedback
    )

    if not k8s_result.get("success"):
        logger.error(f"K8s sandbox failed: {k8s_result.get('error')}")
        return k8s_result

    branch_name = k8s_result["branch_name"]

    # Push to GitHub and create real Pull Request if GitHub is configured
    from .github_client import GitHubClient
    gh_client = GitHubClient()
    gh_pr = None

    if gh_client.is_configured:
        try:
            import subprocess
            logger.info(f"Pushing branch {branch_name} to GitHub remote...")
            # Set remote URL with auth token
            git_url = gh_client.get_authenticated_git_url()
            subprocess.run(["git", "remote", "remove", "origin"], cwd=str(REPO_ROOT), capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", git_url], cwd=str(REPO_ROOT), check=True)
            subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=str(REPO_ROOT), check=True, capture_output=True)

            pr_body = (
                f"### Automated AI Auditor Repair\n\n"
                f"- **Issue:** `{issue_id}`\n"
                f"- **Error:** `{issue.get('error_type')}: {issue.get('error_message')}`\n"
                f"- **Human Feedback:** \"{human_feedback}\"\n"
                f"- **Verified in Sandbox:** Kubernetes Pod `{k8s_result.get('k8s_pod')}`\n\n"
                f"Closes #{issue_id}"
            )
            gh_pr = gh_client.create_pull_request(
                title=f"fix({issue_id}): resolve {issue.get('error_type')} in {rel_path}",
                body=pr_body,
                head_branch=branch_name,
                base_branch="codebase-qa"
            )
        except Exception as e:
            logger.error(f"Failed to push to GitHub or create PR: {e}")

    # Register PR Details
    branch_name = k8s_result["branch_name"]
    pr_details = {
        "title": f"fix({issue_id}): resolve {issue.get('error_type')} in {rel_path}",
        "branch": branch_name,
        "base_branch": "codebase-qa",
        "k8s_pod": k8s_result.get("k8s_pod"),
        "git_diff": k8s_result.get("git_diff"),
        "closes_issue": issue_id,
        "github_pr_url": gh_pr.get("pr_url") if gh_pr else None
    }

    IssueTracker.update_issue(issue_id, {
        "status": "PR_RAISED",
        "human_feedback": human_feedback,
        "pr_details": pr_details
    })

    # Post PR announcement to Slack thread
    pr_url_text = f"\n*GitHub PR:* {gh_pr.get('pr_url')}" if gh_pr else ""
    if thread_ts:
        notifier.post_audit_report(thread_ts, {
            "summary": f"[PR CREATED ON codebase-qa] Verified in Kubernetes Pod {k8s_result.get('k8s_pod')}.{pr_url_text}",
            "root_cause": f"Human review feedback incorporated: \"{human_feedback}\"",
            "severity": "LOW",
            "affected_location": f"{rel_path} (Branch: {branch_name})",
            "suggested_fix": k8s_result.get("git_diff", "")[:600]
        })

    logger.info(f"PR workflow completed for {issue_id} on branch {branch_name}")
    return {
        "success": True,
        "issue_id": issue_id,
        "pr_details": pr_details
    }

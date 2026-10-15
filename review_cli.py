#!/usr/bin/env python
import sys
import json
from audit_agent.issue_tracker import IssueTracker
from audit_agent.review_flow import process_human_review

def print_help():
    print("""
Usage:
  python review_cli.py list
      List all open issues awaiting human review

  python review_cli.py show <ISSUE_ID>
      View details of a specific issue and proposed fix

  python review_cli.py <ISSUE_ID> "<FEEDBACK_OR_APPROVAL>"
      Approve the issue and spin up an isolated Kubernetes Pod
      to apply the fix, validate tests, and raise a PR on codebase-qa.

Examples:
  python review_cli.py list
  python review_cli.py ISSUE-1234 "Approved, go ahead"
  python review_cli.py ISSUE-1234 "Also ensure cart_id is cast to int and handle empty strings"
""")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print_help()
        sys.exit(0)

    cmd = sys.argv[1].strip()

    if cmd == "list":
        issues = IssueTracker.list_open_issues()
        if not issues:
            print("No open issues awaiting review.")
            return

        print("\n" + "=" * 80)
        print("OPEN ISSUES AWAITING HUMAN REVIEW")
        print("=" * 80)
        for iss in issues:
            print(f"ID      : {iss['issue_id']} (Status: {iss['status']})")
            print(f"Error   : {iss['error_type']} - {iss['error_message']}")
            print(f"Endpoint: {iss.get('request', {}).get('method')} {iss.get('request', {}).get('path')}")
            print(f"Summary : {iss.get('proposed_fix', {}).get('summary')}")
            print("-" * 80)
        return

    if cmd == "show":
        if len(sys.argv) < 3:
            print("Please provide an Issue ID: python review_cli.py show <ISSUE_ID>")
            return
        iss_id = sys.argv[2].strip().upper()
        iss = IssueTracker.get_issue(iss_id)
        if not iss:
            print(f"Issue {iss_id} not found.")
            return
        print(json.dumps(iss, indent=2))
        return

    if cmd == "preview":
        if len(sys.argv) < 3:
            print("Please provide an Issue ID: python review_cli.py preview <ISSUE_ID>")
            return
        iss_id = sys.argv[2].strip().upper()
        from audit_agent.port_forwarder import K8sPortForwarder
        import subprocess, time

        pod_name = f"preview-{iss_id.lower()}-{int(time.time() % 1000)}"
        print(f"\n[PREVIEW] Spinning up Kubernetes preview pod: {pod_name}...")
        try:
            # Run pod with server
            subprocess.run([
                "kubectl", "run", pod_name,
                "--image=audit-sandbox:latest",
                "--image-pull-policy=IfNotPresent",
                "--restart=Never",
                "--command", "--", "python3", "-m", "http.server", "8000"
            ], check=True, capture_output=True)

            subprocess.run(["kubectl", "wait", f"pod/{pod_name}", "--for=condition=Ready", "--timeout=20s"], check=True, capture_output=True)

            forwarder = K8sPortForwarder(pod_name)
            if forwarder.start(["8000:8000"]):
                print("=" * 80)
                print(f"LIVE PREVIEW RUNNING FROM KUBERNETES POD: {pod_name}")
                print("=" * 80)
                print("  Backend Server  : http://localhost:8000/")
                print("  Forwarded Ports : 8000 -> 8000 (Pod)")
                print("\nPress Enter to stop preview and clean up pod...")
                input()
            forwarder.stop()
        except Exception as e:
            print(f"Preview error: {e}")
        finally:
            print(f"Cleaning up preview pod {pod_name}...")
            subprocess.run(["kubectl", "delete", "pod", pod_name, "--force", "--grace-period=0"], capture_output=True)
            print("Preview terminated cleanly.")
        return

    # Treat as review command: python review_cli.py <ISSUE_ID> "<FEEDBACK>"
    issue_id = cmd.upper()
    feedback = sys.argv[2] if len(sys.argv) > 2 else "Approved"

    print(f"\n[HUMAN REVIEW] Processing {issue_id} with feedback: \"{feedback}\"")
    print("Launching isolated Kubernetes Pod sandbox in kind cluster...")

    result = process_human_review(issue_id, feedback)

    if result.get("success"):
        pr = result.get("pr_details", {})
        print("\n" + "=" * 80)
        print("SUCCESS: PULL REQUEST CREATED FROM KUBERNETES SANDBOX")
        print("=" * 80)
        print(f"Issue        : {issue_id}")
        print(f"Branch       : {pr.get('branch')} -> {pr.get('base_branch')}")
        print(f"Commit Hash  : {pr.get('commit_hash')}")
        print(f"Verified In  : Kubernetes Pod ({pr.get('k8s_pod')})")
        print(f"Slack Thread : Updated with diff and PR status")
        print("\nGit Diff:")
        print(pr.get("git_diff"))
        print("=" * 80)
    else:
        print("\nFAILURE: Kubernetes sandbox execution failed:")
        print(result.get("error"))

if __name__ == "__main__":
    main()

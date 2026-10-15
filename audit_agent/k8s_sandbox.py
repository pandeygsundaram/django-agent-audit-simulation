import subprocess
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class KubernetesSandboxRunner:
    """
    Spawns an isolated Kubernetes Pod to execute code repairs,
    run validation checks, and commit to a bug-fix branch.
    """

    def __init__(self, repo_root: str, namespace: str = "default", image: str = "audit-sandbox:latest"):
        self.repo_root = Path(repo_root).resolve()
        self.namespace = namespace
        self.image = image

    def run_k8s_repair(
        self,
        issue_id: str,
        relative_file_path: str,
        updated_file_content: str,
        summary: str,
        human_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the repair inside an isolated Kubernetes Pod:
        1. Spawns Pod: audit-sandbox-<issue_id>
        2. Copies repository into /workspace
        3. Checks out codebase-qa and creates bug-fix/<issue_id>-<timestamp>
        4. Writes updated_file_content into the sandbox target file
        5. Validates syntax and Django checks inside the Pod
        6. Commits changes inside Pod
        7. Syncs branch back to host repo
        8. Deletes the Pod
        """
        timestamp = int(time.time())
        clean_issue = issue_id.lower().replace("_", "-")
        pod_name = f"audit-sandbox-{clean_issue}-{timestamp % 10000}"
        branch_name = f"bug-fix/{clean_issue}-{timestamp}"

        logger.info(f"[K8s Sandbox] Launching pod {pod_name} in namespace {self.namespace}")

        try:
            # 1. Create Pod
            create_cmd = [
                "kubectl", "run", pod_name,
                f"--image={self.image}",
                "--image-pull-policy=IfNotPresent",
                f"--namespace={self.namespace}",
                "--restart=Never",
                "--command", "--", "sleep", "120"
            ]
            subprocess.run(create_cmd, check=True, capture_output=True, text=True)

            # 2. Wait for Pod to be Running
            logger.info(f"[K8s Sandbox] Waiting for {pod_name} to be ready...")
            wait_cmd = [
                "kubectl", "wait", f"pod/{pod_name}",
                f"--namespace={self.namespace}",
                "--for=condition=Ready",
                "--timeout=30s"
            ]
            subprocess.run(wait_cmd, check=True, capture_output=True, text=True)

            # 3. Create /workspace and copy repo files
            subprocess.run(
                ["kubectl", "exec", pod_name, f"-n={self.namespace}", "--", "mkdir", "-p", "/workspace"],
                check=True, capture_output=True
            )

            logger.info(f"[K8s Sandbox] Copying codebase into pod {pod_name}:/workspace")
            for item in ["demo_app", "core_audit", "settings.py", "manage.py", ".git"]:
                src_path = self.repo_root / item
                if src_path.exists():
                    subprocess.run(
                        ["kubectl", "cp", str(src_path), f"{self.namespace}/{pod_name}:/workspace/{item}"],
                        check=True, capture_output=True
                    )

            # 4. Configure git inside pod and create branch
            init_git_script = f"""
cd /workspace
git config user.name "AI-Auditor-Bot"
git config user.email "bot@backend-auditor.local"
git checkout codebase-qa
git checkout -b {branch_name}
"""
            subprocess.run(
                ["kubectl", "exec", pod_name, f"-n={self.namespace}", "--", "bash", "-c", init_git_script],
                check=True, capture_output=True, text=True
            )

            # 5. Write the updated file content inside Pod
            target_path_in_pod = f"/workspace/{relative_file_path}"
            # Use base64 encoding to prevent any quoting or escaping issues
            import base64
            b64_content = base64.b64encode(updated_file_content.encode("utf-8")).decode("ascii")
            write_script = f"echo '{b64_content}' | base64 -d > {target_path_in_pod}"
            subprocess.run(
                ["kubectl", "exec", pod_name, f"-n={self.namespace}", "--", "bash", "-c", write_script],
                check=True, capture_output=True, text=True
            )

            # 6. Run syntax validation inside Pod
            compile_res = subprocess.run(
                ["kubectl", "exec", pod_name, f"-n={self.namespace}", "--", "python3", "-m", "py_compile", target_path_in_pod],
                capture_output=True, text=True
            )
            if compile_res.returncode != 0:
                raise ValueError(f"Syntax compile failed inside K8s pod: {compile_res.stderr}")

            # Run Django check inside Pod
            django_check_res = subprocess.run(
                ["kubectl", "exec", pod_name, f"-n={self.namespace}", "--", "python3", "manage.py", "check"],
                capture_output=True, text=True
            )
            if django_check_res.returncode != 0:
                raise ValueError(f"Django check failed inside K8s pod: {django_check_res.stderr}")

            # 7. Commit changes inside Pod
            commit_msg = (
                f"fix({issue_id}): resolve error in {relative_file_path}\n\n"
                f"Summary: {summary}\n"
                f"Human Feedback: {human_feedback or 'None'}\n"
                f"Verified inside Kubernetes Pod: {pod_name}"
            )
            commit_script = f"""
cd /workspace
git add {relative_file_path}
git commit -m "{commit_msg}"
"""
            subprocess.run(
                ["kubectl", "exec", pod_name, f"-n={self.namespace}", "--", "bash", "-c", commit_script],
                check=True, capture_output=True, text=True
            )

            # 8. Sync the created branch back to host repo
            # Switch back host repo to codebase-qa, create branch and commit
            subprocess.run(
                ["git", "checkout", "-b", branch_name, "codebase-qa"],
                cwd=str(self.repo_root), check=True, capture_output=True
            )
            (self.repo_root / relative_file_path).write_text(updated_file_content, encoding="utf-8")
            subprocess.run(["git", "add", relative_file_path], cwd=str(self.repo_root), check=True)
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(self.repo_root), check=True)
            subprocess.run(["git", "checkout", "main"], cwd=str(self.repo_root), check=True)

            # 9. Get git diff against codebase-qa
            diff_res = subprocess.run(
                ["git", "diff", f"codebase-qa...{branch_name}"],
                cwd=str(self.repo_root), capture_output=True, text=True
            )
            git_diff = diff_res.stdout

            return {
                "success": True,
                "k8s_pod": pod_name,
                "branch_name": branch_name,
                "base_branch": "codebase-qa",
                "commit_hash": branch_name,
                "git_diff": git_diff,
                "target_file": relative_file_path,
                "human_feedback": human_feedback
            }

        except Exception as e:
            logger.error(f"[K8s Sandbox] Execution error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "k8s_pod": pod_name,
                "branch_name": branch_name
            }
        finally:
            logger.info(f"[K8s Sandbox] Deleting pod {pod_name}")
            subprocess.run(
                ["kubectl", "delete", "pod", pod_name, f"-n={self.namespace}", "--force", "--grace-period=0"],
                capture_output=True
            )

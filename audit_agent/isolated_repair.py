import os
import shutil
import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class IsolatedRepairSandbox:
    """
    Spawns an isolated git worktree environment to apply fixes,
    runs verification checks (syntax & django check), commits the fix
    to a bug-fix branch, and cleans up the sandbox.
    """

    def __init__(self, repo_root: str, base_branch: str = "codebase-qa"):
        self.repo_root = Path(repo_root).resolve()
        self.base_branch = base_branch
        self.sandboxes_dir = self.repo_root / "sandboxes"
        self.sandboxes_dir.mkdir(exist_ok=True)

    def run_isolated_fix(
        self,
        error_type: str,
        relative_file_path: str,
        original_code: str,
        fixed_code: str,
        summary: str
    ) -> Dict[str, Any]:
        """
        Executes the full sandbox lifecycle:
        1. Creates isolated worktree on new bug-fix branch.
        2. Applies the fix to the file in the isolated directory.
        3. Validates with py_compile and Django checks.
        4. Commits to the bug-fix branch.
        5. Cleans up the worktree directory.
        """
        timestamp = int(time.time())
        branch_name = f"bug-fix/{error_type.lower()}-{timestamp}"
        sandbox_path = self.sandboxes_dir / f"sandbox-{timestamp}"

        try:
            # Step 1: Ensure base branch exists and create isolated worktree
            logger.info(f"Creating isolated worktree at {sandbox_path} from {self.base_branch}")
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(sandbox_path), self.base_branch],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True
            )

            # Step 2: Target file in sandbox
            target_file = sandbox_path / relative_file_path
            if not target_file.exists():
                return {
                    "success": False,
                    "error": f"Target file does not exist in sandbox: {relative_file_path}",
                    "branch_name": branch_name
                }

            file_content = target_file.read_text(encoding="utf-8")

            # Clean snippets for matching
            orig_stripped = original_code.strip()
            fix_stripped = fixed_code.strip()

            # Attempt replacement
            if orig_stripped and orig_stripped in file_content:
                new_file_content = file_content.replace(orig_stripped, fix_stripped, 1)
            else:
                # If exact block match fails, try fuzzy line-based search
                lines = file_content.splitlines()
                first_orig_line = orig_stripped.splitlines()[0].strip() if orig_stripped else ""
                matched_idx = -1
                for idx, line in enumerate(lines):
                    if first_orig_line and first_orig_line in line:
                        matched_idx = idx
                        break

                if matched_idx != -1:
                    orig_line_count = len(orig_stripped.splitlines())
                    lines[matched_idx:matched_idx + orig_line_count] = [fix_stripped]
                    new_file_content = "\n".join(lines) + "\n"
                else:
                    return {
                        "success": False,
                        "error": "Could not locate original code block in target file to apply replacement.",
                        "branch_name": branch_name
                    }

            # Write fixed code into sandbox file
            target_file.write_text(new_file_content, encoding="utf-8")

            # Step 3: Verify syntax in sandbox
            compile_res = subprocess.run(
                ["python3", "-m", "py_compile", str(target_file)],
                capture_output=True,
                text=True
            )
            if compile_res.returncode != 0:
                return {
                    "success": False,
                    "error": f"Syntax verification failed: {compile_res.stderr}",
                    "branch_name": branch_name
                }

            # Verify Django system check in sandbox
            venv_python = self.repo_root / ".venv" / "bin" / "python"
            python_bin = str(venv_python) if venv_python.exists() else "python3"

            check_res = subprocess.run(
                [python_bin, "manage.py", "check"],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True
            )
            if check_res.returncode != 0:
                return {
                    "success": False,
                    "error": f"Django manage.py check failed: {check_res.stderr}",
                    "branch_name": branch_name
                }

            # Step 4: Get diff before commit
            diff_res = subprocess.run(
                ["git", "diff", relative_file_path],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True
            )
            git_diff = diff_res.stdout

            # Step 5: Commit changes to bug-fix branch
            subprocess.run(["git", "add", relative_file_path], cwd=str(sandbox_path), check=True)
            commit_msg = f"fix(audit): resolve {error_type} in {relative_file_path}\n\nSummary: {summary}\nBase Branch: {self.base_branch}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(sandbox_path), check=True)

            # Get commit hash
            hash_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True
            )
            commit_hash = hash_res.stdout.strip()

            # Attempt git push if remote origin is configured
            remote_pushed = False
            try:
                remotes = subprocess.run(
                    ["git", "remote"],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True
                )
                if "origin" in remotes.stdout:
                    subprocess.run(
                        ["git", "push", "-u", "origin", branch_name],
                        cwd=str(self.repo_root),
                        check=True,
                        capture_output=True
                    )
                    remote_pushed = True
            except Exception as e:
                logger.warning(f"Remote push skipped or failed: {e}")

            return {
                "success": True,
                "branch_name": branch_name,
                "commit_hash": commit_hash[:8],
                "base_branch": self.base_branch,
                "git_diff": git_diff,
                "target_file": relative_file_path,
                "remote_pushed": remote_pushed
            }

        except Exception as e:
            logger.error(f"Isolated repair failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "branch_name": branch_name
            }
        finally:
            # Step 6: Cleanup isolated worktree directory
            if sandbox_path.exists():
                logger.info(f"Cleaning up sandbox at {sandbox_path}")
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(sandbox_path)],
                    cwd=str(self.repo_root),
                    capture_output=True
                )
                if sandbox_path.exists():
                    shutil.rmtree(sandbox_path, ignore_errors=True)

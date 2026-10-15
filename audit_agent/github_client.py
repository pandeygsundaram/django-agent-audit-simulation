import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class GitHubClient:
    """
    Manages GitHub Issues, Branch Pushes, and Pull Requests
    via GitHub REST API and authenticated Git.
    """

    def __init__(self, token: Optional[str] = None, repo_slug: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "").strip()
        self.repo_slug = repo_slug or os.getenv("GITHUB_REPO", "").strip()  # e.g. "owner/repo"
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Django-AI-Auditor-Bot"
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.repo_slug and "/" in self.repo_slug)

    def create_issue(self, title: str, body: str, labels: list = None) -> Optional[Dict[str, Any]]:
        """
        Creates a real GitHub Issue in the repository.
        """
        if not self.is_configured:
            logger.info("GitHub not configured; skipping remote issue creation.")
            return None

        url = f"{self.base_url}/repos/{self.repo_slug}/issues"
        payload = {
            "title": title,
            "body": body,
            "labels": labels or ["bug", "ai-audited"]
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            if resp.status_code in [200, 201]:
                data = resp.json()
                logger.info(f"Created GitHub Issue #{data.get('number')}: {data.get('html_url')}")
                return {
                    "issue_number": data.get("number"),
                    "issue_url": data.get("html_url")
                }
            else:
                logger.error(f"GitHub Issue creation failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            logger.error(f"GitHub API error creating issue: {e}")
            return None

    def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "codebase-qa"
    ) -> Optional[Dict[str, Any]]:
        """
        Opens a real Pull Request from head_branch to base_branch on GitHub.
        """
        if not self.is_configured:
            logger.info("GitHub not configured; skipping remote PR creation.")
            return None

        url = f"{self.base_url}/repos/{self.repo_slug}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            if resp.status_code in [200, 201]:
                data = resp.json()
                logger.info(f"Created GitHub PR #{data.get('number')}: {data.get('html_url')}")
                return {
                    "pr_number": data.get("number"),
                    "pr_url": data.get("html_url")
                }
            else:
                logger.error(f"GitHub PR creation failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            logger.error(f"GitHub API error creating PR: {e}")
            return None

    def get_authenticated_git_url(self) -> str:
        """
        Returns remote git push URL with embedded auth token.
        """
        if not self.is_configured:
            return ""
        return f"https://x-access-token:{self.token}@github.com/{self.repo_slug}.git"

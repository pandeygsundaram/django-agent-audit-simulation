import time
import json
import logging
import requests
from typing import Dict, Any, Optional
import config

logger = logging.getLogger(__name__)

# Initialize Slack SDK if token is provided
slack_web_client = None
if config.SLACK_BOT_TOKEN:
    try:
        from slack_sdk import WebClient
        slack_web_client = WebClient(token=config.SLACK_BOT_TOKEN)
    except Exception as e:
        logger.warning(f"Could not initialize Slack WebClient: {e}")

class SlackAuditorNotifier:
    """
    Handles posting error alerts and threaded AI audit responses to Slack.
    Supports real Slack Bot, incoming webhook, or console simulation.
    """

    def __init__(self):
        self.bot_token = config.SLACK_BOT_TOKEN
        self.channel = config.SLACK_CHANNEL
        self.webhook_url = config.SLACK_WEBHOOK_URL
        self.is_mock = config.USE_MOCK_SLACK

    def post_initial_alert(self, event_data: Dict[str, Any]) -> str:
        """
        Sends initial alert to Slack channel and returns a thread timestamp (ts).
        """
        error_type = event_data.get("error_type", "BackendError")
        error_msg = event_data.get("error_message", "Unknown error")
        req = event_data.get("request", {})
        method = req.get("method", "N/A")
        path = req.get("path", "N/A")
        source = event_data.get("source", "Backend")

        text_fallback = f"[ALERT] [{error_type}] in {method} {path}: {error_msg}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"[ALERT] Backend Exception: {error_type}",
                    "emoji": False
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Source:*\n`{source}`"},
                    {"type": "mrkdwn", "text": f"*Endpoint:*\n`{method} {path}`"},
                    {"type": "mrkdwn", "text": f"*Error Message:*\n`{error_msg}`"},
                    {"type": "mrkdwn", "text": f"*Client IP:*\n`{req.get('client_ip', '127.0.0.1')}`"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "*[AI Auditor Agent spawned]* Investigating stack frames and code context..."}
                ]
            }
        ]

        if not self.is_mock and slack_web_client:
            try:
                resp = slack_web_client.chat_postMessage(
                    channel=self.channel,
                    text=text_fallback,
                    blocks=blocks
                )
                return resp["ts"]
            except Exception as e:
                logger.error(f"Failed to post alert via Slack WebClient: {e}")

        if not self.is_mock and self.webhook_url:
            try:
                resp = requests.post(self.webhook_url, json={"text": text_fallback, "blocks": blocks}, timeout=5)
                return str(time.time())
            except Exception as e:
                logger.error(f"Failed to post alert via Slack Webhook: {e}")

        # Console / Mock Fallback
        mock_ts = f"mock-thread-{int(time.time() * 1000)}"
        print("\n" + "="*80)
        print(f"📢 [SLACK CHANNEL: {self.channel}] (Simulated Alert Sent)")
        print(f"🚨 ALERT: {error_type} in {method} {path}")
        print(f"   Message: {error_msg}")
        print(f"   Source : {source}")
        print(f"   Thread ID: {mock_ts}")
        print("   Status : 🤖 Auditor Agent dispatched to investigate...")
        print("="*80 + "\n")
        return mock_ts

    def post_audit_report(self, thread_ts: str, audit_report: Dict[str, Any]):
        """
        Replies in the Slack thread with the complete AI audit report.
        """
        summary = audit_report.get("summary", "Analysis complete.")
        root_cause = audit_report.get("root_cause", "N/A")
        severity = audit_report.get("severity", "MEDIUM")
        file_line = audit_report.get("affected_location", "N/A")
        fix_code = audit_report.get("suggested_fix", "")

        markdown_body = (
            f"*AI Audit Report* `[{severity.upper()}]`\n\n"
            f"*Summary:* {summary}\n\n"
            f"*Location:* `{file_line}`\n\n"
            f"*Root Cause:*\n{root_cause}\n\n"
            f"*Suggested Fix:*\n```python\n{fix_code}\n```"
        )

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*AI Audit Findings* `[{severity.upper()}]`"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n`{severity.upper()}`"},
                    {"type": "mrkdwn", "text": f"*Culprit File:*\n`{file_line}`"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Suggested Fix / Patch:*\n```python\n{fix_code}\n```"}
            }
        ]

        if not self.is_mock and slack_web_client:
            try:
                slack_web_client.chat_postMessage(
                    channel=self.channel,
                    thread_ts=thread_ts,
                    text=markdown_body,
                    blocks=blocks
                )
                return
            except Exception as e:
                logger.error(f"Failed to post audit reply in Slack thread: {e}")

        # Console / Mock Fallback
        print("\n" + "#"*80)
        print(f"💬 [SLACK THREAD REPLY: {thread_ts}]")
        print(f"Severity : {severity_emoji} {severity.upper()}")
        print(f"Location : {file_line}")
        print(f"Summary  : {summary}")
        print(f"Cause    : {root_cause}")
        print("Suggested Fix:")
        print("-" * 40)
        for line in fix_code.splitlines():
            print(f"  {line}")
        print("-" * 40)
        print("#"*80 + "\n")

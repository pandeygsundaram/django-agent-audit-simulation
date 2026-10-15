import logging
from typing import Dict, Any
from .slack_client import SlackAuditorNotifier
from .context_extractor import build_agent_context
from .agent import AuditorAgent

logger = logging.getLogger(__name__)

# Singletons
notifier = SlackAuditorNotifier()
agent = AuditorAgent()

def run_audit_pipeline(event_data: Dict[str, Any]):
    """
    Executes the 3-step audit process:
    1. Send initial alert to Slack channel.
    2. Extract code context and traceback frames.
    3. Run AI agent and reply in Slack thread.
    """
    error_type = event_data.get("error_type", "BackendError")
    logger.info(f"⚡ [Pipeline] Processing error event: {error_type}")

    # Step 1: Fire message on Slack channel
    thread_ts = notifier.post_initial_alert(event_data)

    # Step 2: Extract code context & frames from repository
    enriched_context = build_agent_context(event_data)

    # Step 3: Spawn Agent to audit root cause and fix
    audit_report = agent.audit(enriched_context)

    # Step 4: Reply in the Slack thread
    notifier.post_audit_report(thread_ts, audit_report)

    logger.info(f"✅ [Pipeline] Audit complete for {error_type}. Posted to thread {thread_ts}")
    return audit_report

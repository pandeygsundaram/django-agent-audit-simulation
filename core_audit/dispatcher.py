import threading
import logging
import traceback
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Thread-local storage to prevent duplicate alerts if both middleware and logging handler trigger
_thread_locals = threading.local()

def mark_exception_handled():
    _thread_locals.exception_handled = True

def is_exception_handled():
    return getattr(_thread_locals, "exception_handled", False)

def clear_exception_handled():
    _thread_locals.exception_handled = False

def dispatch_error_event(event_data: Dict[str, Any]):
    """
    Dispatches the error event to the Audit & Slack pipeline in a background thread.
    This ensures Django HTTP response is never blocked by Slack or LLM API calls.
    """
    from audit_agent.pipeline import run_audit_pipeline

    def _worker():
        try:
            run_audit_pipeline(event_data)
        except Exception as e:
            logger.error(f"Error executing audit pipeline: {e}", exc_info=True)

    thread = threading.Thread(target=_worker, name=f"AuditWorker-{event_data.get('error_type')}", daemon=True)
    thread.start()

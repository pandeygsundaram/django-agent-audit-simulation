import json
import traceback
import logging
from django.utils.deprecation import MiddlewareMixin
from .dispatcher import dispatch_error_event, mark_exception_handled, clear_exception_handled

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "cookie", "api_key", "card", "cvv"}

def sanitize_dict(d):
    if not isinstance(d, dict):
        return d
    sanitized = {}
    for k, v in d.items():
        if any(sens in k.lower() for sens in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        else:
            sanitized[k] = v
    return sanitized

class AuditExceptionMiddleware(MiddlewareMixin):
    """
    Django middleware to intercept unhandled exceptions, extract request context,
    and dispatch an error event to the AI audit pipeline.
    """

    def process_request(self, request):
        clear_exception_handled()
        return None

    def process_exception(self, request, exception):
        mark_exception_handled()

        # Sanitize query parameters
        query_params = sanitize_dict(dict(request.GET.items()))

        # Sanitize body if JSON
        body_data = "[EMPTY]"
        if request.body:
            try:
                raw_json = json.loads(request.body.decode("utf-8", errors="replace"))
                body_data = sanitize_dict(raw_json)
            except Exception:
                body_data = request.body.decode("utf-8", errors="replace")[:500]

        # Extract headers (sanitized)
        headers = {}
        for key, value in request.META.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                if any(sens in header_name.lower() for sens in SENSITIVE_KEYS):
                    headers[header_name] = "[REDACTED]"
                else:
                    headers[header_name] = value

        event_data = {
            "source": "Django Middleware (process_exception)",
            "error_type": exception.__class__.__name__,
            "error_message": str(exception),
            "traceback": traceback.format_exc(),
            "request": {
                "method": request.method,
                "path": request.path,
                "query_params": query_params,
                "body": body_data,
                "headers": headers,
                "user": str(getattr(request, "user", "AnonymousUser")),
                "client_ip": request.META.get("REMOTE_ADDR", "127.0.0.1"),
            }
        }

        dispatch_error_event(event_data)
        # Returning None allows Django's standard 500 handler to proceed normally
        return None

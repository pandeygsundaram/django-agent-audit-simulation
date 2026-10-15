import logging
import traceback
from .dispatcher import dispatch_error_event, is_exception_handled

class AuditLoggingHandler(logging.Handler):
    """
    Python logging handler that captures logger.error or logger.critical calls
    with exception info and forwards them to the AI audit pipeline.
    """

    def emit(self, record):
        try:
            # If already captured by middleware in this thread, skip duplicate alert
            if is_exception_handled():
                return

            # Skip generic Django response status logs without actual exception tracebacks
            if not record.exc_info and any(record.getMessage().startswith(prefix) for prefix in ["Internal Server Error:", "Bad Gateway:", "Not Found:"]):
                return

            # Format traceback if exc_info exists
            tb_str = ""
            err_type = "LoggedError"
            err_msg = record.getMessage()

            if record.exc_info:
                exc_type, exc_val, exc_tb = record.exc_info
                if exc_type:
                    err_type = exc_type.__name__
                if exc_val:
                    err_msg = str(exc_val)
                tb_str = "".join(traceback.format_exception(*record.exc_info))
            else:
                tb_str = f"Logged from {record.pathname}:{record.lineno} in {record.funcName}\nMessage: {err_msg}"

            event_data = {
                "source": f"Django Logger ({record.name})",
                "error_type": err_type,
                "error_message": err_msg,
                "traceback": tb_str,
                "logger_name": record.name,
                "log_level": record.levelname,
                "file_location": f"{record.pathname}:{record.lineno}",
                "request": {
                    "method": getattr(record, "request_method", "N/A"),
                    "path": getattr(record, "request_path", "N/A"),
                    "user": "N/A",
                    "body": "N/A",
                }
            }

            dispatch_error_event(event_data)
        except Exception:
            self.handleError(record)

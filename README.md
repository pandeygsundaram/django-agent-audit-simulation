# Standalone Django AI Auditor Agent Prototype

This prototype listens to backend errors in a Django app, notifies a Slack channel, spawns an AI Auditor Agent with full code context, and replies in the Slack thread with the root cause and a suggested code patch.

---

## Architecture Flow

1. **Interception**:
   - `core_audit/middleware.py`: Catches unhandled 500 exceptions in Django views (`process_exception`).
   - `core_audit/handlers.py`: Intercepts `logger.error` / `logger.critical` calls with `exc_info=True`.
2. **Slack Alert**:
   - `audit_agent/slack_client.py`: Posts an immediate alert to `#backend-alerts` and captures the message `ts` (thread ID).
3. **Context Extraction**:
   - `audit_agent/context_extractor.py`: Parses the traceback, filters for project source files, and extracts surrounding code lines.
4. **AI Reasoning**:
   - `audit_agent/agent.py`: Evaluates request context, traceback, and source code to output:
     - Plain-English Summary
     - Root Cause Analysis
     - Severity Rating
     - Suggested Code Fix (Patch)
5. **Threaded Resolution**:
   - Posts the full audit report as a threaded reply under the original Slack alert.

---

## Project Structure

```
django-agent-audit-simulation/
├── .env.example             # Template for Slack token/webhook and Gemini API key
├── config.py                # Environment configuration loader
├── settings.py              # Django settings (DEBUG=False, custom middleware & logger)
├── server.py                # Live HTTP server runner (http://127.0.0.1:8000)
├── trigger_test.py          # Automated test suite firing 5 bug endpoints
│
├── core_audit/              # Django integration package
│   ├── middleware.py        # AuditExceptionMiddleware
│   ├── handlers.py          # AuditLoggingHandler
│   └── dispatcher.py        # Non-blocking async thread dispatcher
│
├── audit_agent/             # AI & Slack Agent package
│   ├── pipeline.py          # Pipeline coordinator
│   ├── context_extractor.py # Traceback parser & code extractor
│   ├── agent.py             # Auditor Agent (Gemini / Heuristic fallback)
│   └── slack_client.py      # Slack WebClient / Webhook / Console mock
│
└── demo_app/                # Buggy demo endpoints
    ├── views.py             # KeyError, ZeroDivisionError, AttributeError, etc.
    └── urls.py              # URL routing
```

---

## Quick Start & Verification

### Option A: Run the Automated Verification Suite
```bash
cd /home/sundaram/django-agent-audit-simulation
.venv/bin/python trigger_test.py
```

### Option B: Run the Live HTTP Server
```bash
cd /home/sundaram/django-agent-audit-simulation
.venv/bin/python server.py
```
In another terminal, trigger any bug:
```bash
# 1. KeyError
curl -X POST http://127.0.0.1:8000/api/checkout/ -d '{"cart_id": 101}' -H "Content-Type: application/json"

# 2. ZeroDivisionError
curl "http://127.0.0.1:8000/api/calculate-discount/?items=0"

# 3. AttributeError (NoneType)
curl "http://127.0.0.1:8000/api/user-profile/?user_id=ghost"

# 4. Logger.error
curl "http://127.0.0.1:8000/api/manual-error/"
```

---

## Connecting Live Slack & Gemini API

Create `.env` in this directory:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
# Real Slack Bot Token (starts with xoxb-...)
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL=#backend-alerts

# Or Slack Incoming Webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Gemini API Key (for LLM reasoning)
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.5-flash
```
*Note: If no keys are provided, the prototype automatically runs in offline simulation mode using clean console logs and heuristic analysis!*

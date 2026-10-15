import json
import logging
from typing import Dict, Any
import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite Django SRE and Backend Auditor Agent.
You are called when an uncaught exception or error occurs in production.
You are provided with:
1. Error type and message
2. HTTP Request details (method, path, sanitized body, query params)
3. Culprit stack frames with exact source code lines extracted around the crash.

Your job is to analyze the context and provide a structured JSON response with the following schema:
{
  "summary": "1-2 sentence plain-English summary of what broke",
  "root_cause": "Detailed technical explanation of why the crash occurred, citing exact variables or missing validations",
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "affected_location": "path/to/file.py:line_number (function_name)",
  "suggested_fix": "Clean, copy-pasteable Python code snippet showing the fix or defensive check"
}

Respond ONLY with valid JSON. Do not wrap in markdown quotes if possible, or use standard ```json blocks.
"""

def heuristic_audit(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based auditor used as an instant offline fallback.
    """
    err_type = context.get("error_type", "")
    err_msg = context.get("error_message", "")
    req = context.get("request", {})
    frame = context.get("primary_frame") or {}
    file_path = frame.get("file", "unknown")
    line = frame.get("line", 0)
    func = frame.get("function", "unknown")
    loc_str = f"{file_path}:{line} in {func}()"

    if "KeyError" in err_type:
        key_name = err_msg.strip("'\"")
        return {
            "summary": f"Unhandled KeyError when accessing missing key '{key_name}' in request data.",
            "root_cause": f"The endpoint expected '{key_name}' in the request payload or dictionary, but the client did not send it. Accessing dict['{key_name}'] directly without .get() or schema validation raised KeyError.",
            "severity": "MEDIUM",
            "affected_location": loc_str,
            "suggested_fix": (
                f"# Use dict.get() with fallback or validate incoming data:\n"
                f"{key_name} = data.get('{key_name}')\n"
                f"if not {key_name}:\n"
                f"    return JsonResponse({{'error': 'Missing required parameter: {key_name}'}}, status=400)"
            )
        }
    elif "ZeroDivisionError" in err_type:
        return {
            "summary": "ZeroDivisionError in mathematical computation / rate calculation.",
            "root_cause": "A divisor variable evaluated to zero (e.g. items_count=0), causing a direct division by zero without guard rails.",
            "severity": "MEDIUM",
            "affected_location": loc_str,
            "suggested_fix": (
                "# Add guard check before division:\n"
                "if items_count <= 0:\n"
                "    return JsonResponse({'error': 'items count must be greater than zero'}, status=400)\n"
                "discount_per_item = total_discount / items_count"
            )
        }
    elif "AttributeError" in err_type or "NoneType" in err_msg:
        return {
            "summary": "AttributeError caused by dereferencing a None object.",
            "root_cause": f"A database query or lookup returned None instead of an active record/object. The code immediately tried to access an attribute on None without checking existence.",
            "severity": "HIGH",
            "affected_location": loc_str,
            "suggested_fix": (
                "if not user_record:\n"
                "    return JsonResponse({'error': 'Requested user was not found'}, status=404)\n"
                "email = getattr(user_record, 'email', None) or user_record.get('email')"
            )
        }
    elif "ConnectionResetError" in err_type or "Connection" in err_msg:
        return {
            "summary": "Downstream external dependency network disconnect.",
            "root_cause": "The remote service connection was forcibly reset or closed during an outbound HTTP or socket operation.",
            "severity": "HIGH",
            "affected_location": loc_str,
            "suggested_fix": (
                "# Wrap in retry mechanism with exponential backoff:\n"
                "from requests.adapters import HTTPAdapter\n"
                "from urllib3.util.retry import Retry\n\n"
                "# Configure retry strategy with 3 attempts and status_forcelist=[502, 503, 504]"
            )
        }

    return {
        "summary": f"Unhandled {err_type}: {err_msg}",
        "root_cause": f"Exception raised at {loc_str}. Traceback indicates unexpected runtime state.",
        "severity": "MEDIUM",
        "affected_location": loc_str,
        "suggested_fix": (
            "try:\n"
            "    # Risky operation\n"
            "    pass\n"
            "except Exception as e:\n"
            "    logger.exception('Handled error gracefully')\n"
            "    return JsonResponse({'error': 'Internal server error'}, status=500)"
        )
    }

class AuditorAgent:
    """
    AI Agent that reasons about backend errors with code context and request traces.
    Supports Groq (Llama 3.3 / Llama 3.1), Google Gemini, or offline heuristic fallback.
    """

    def __init__(self):
        self.groq_api_key = config.GROQ_API_KEY
        self.groq_model = config.GROQ_MODEL
        self.gemini_api_key = config.GEMINI_API_KEY
        self.gemini_model = config.GEMINI_MODEL
        self.use_mock = config.USE_MOCK_LLM

    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        return f"""
ERROR DETAILS:
- Error Type: {context.get('error_type')}
- Message: {context.get('error_message')}
- Source: {context.get('source')}

REQUEST CONTEXT:
- Method: {context.get('request', {}).get('method')}
- Path: {context.get('request', {}).get('path')}
- Query Params: {json.dumps(context.get('request', {}).get('query_params', {}))}
- Body: {json.dumps(context.get('request', {}).get('body', {}))}

SOURCE CODE CONTEXT (Extracted from repository):
File: {context.get('primary_frame', {}).get('file', 'N/A')}
Line: {context.get('primary_frame', {}).get('line', 'N/A')}
Function: {context.get('primary_frame', {}).get('function', 'N/A')}

```python
{context.get('primary_frame', {}).get('code_snippet', 'No snippet available')}
```

RAW TRACEBACK:
{context.get('raw_traceback')}

Generate your audit report as JSON now.
"""

    def audit(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes audit reasoning using Groq API, Gemini API, or heuristic fallback.
        """
        user_prompt = self._build_user_prompt(context)

        # 1. Groq Integration
        if self.groq_api_key:
            try:
                from groq import Groq
                client = Groq(api_key=self.groq_api_key)
                completion = client.chat.completions.create(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                result_text = completion.choices[0].message.content.strip()
                return json.loads(result_text)
            except Exception as e:
                logger.error(f"Groq API call failed: {e}")
                fallback = heuristic_audit(context)
                fallback["summary"] += f" (Note: Groq error: {e})"
                return fallback

        # 2. Gemini Integration
        if self.gemini_api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.gemini_api_key)
                response = client.models.generate_content(
                    model=self.gemini_model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.2,
                        response_mime_type="application/json"
                    )
                )

                result_text = response.text.strip()
                if result_text.startswith("```json"):
                    result_text = result_text[7:]
                if result_text.startswith("```"):
                    result_text = result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3]

                return json.loads(result_text.strip())
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                fallback = heuristic_audit(context)
                fallback["summary"] += f" (Note: Gemini error: {e})"
                return fallback

        # 3. Heuristic offline fallback
        return heuristic_audit(context)

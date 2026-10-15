#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    from django.core.management import execute_from_command_line
    print("""
========================================================================
🚀 Standalone Django Audit Simulation Server
========================================================================
Server running at http://127.0.0.1:8000/

Available Test Endpoints:
  1. GET  /health/
     Normal healthy endpoint (200 OK)

  2. POST /api/checkout/
     Triggers KeyError (Missing 'payment_method')
     Example: curl -X POST http://127.0.0.1:8000/api/checkout/ -d '{"cart_id": 12}' -H "Content-Type: application/json"

  3. GET  /api/calculate-discount/?items=0
     Triggers ZeroDivisionError (Division by 0)
     Example: curl "http://127.0.0.1:8000/api/calculate-discount/?items=0"

  4. GET  /api/user-profile/?user_id=ghost
     Triggers AttributeError (NoneType dereference)
     Example: curl "http://127.0.0.1:8000/api/user-profile/?user_id=ghost"

  5. GET  /api/manual-error/
     Triggers direct logger.error (ConnectionResetError)
     Example: curl "http://127.0.0.1:8000/api/manual-error/"
========================================================================
""")
    execute_from_command_line(["manage.py", "runserver", "127.0.0.1:8000", "--noreload"])

if __name__ == "__main__":
    main()

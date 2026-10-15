import os
import sys
import time
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django
django.setup()

from django.test import Client

def run_tests():
    client = Client()
    print("=" * 80)
    print("🚀 STARTING STANDALONE DJANGO AUDIT AGENT SIMULATION TEST")
    print("=" * 80)

    # 1. Health check
    print("\n👉 [TEST 1] Calling /health/ (Expected: 200 OK)")
    resp = client.get("/health/")
    print(f"Status Code: {resp.status_code}, Response: {resp.json()}")

    # 2. KeyError Bug
    print("\n👉 [TEST 2] Triggering Bug 1: POST /api/checkout/ without 'payment_method'")
    try:
        resp = client.post(
            "/api/checkout/",
            data=json.dumps({"cart_id": 9999}),
            content_type="application/json"
        )
        print(f"Server returned status code: {resp.status_code}")
    except Exception as e:
        print(f"Client caught: {e}")
    time.sleep(1.5)  # Wait for background thread to run pipeline

    # 3. ZeroDivisionError Bug
    print("\n👉 [TEST 3] Triggering Bug 2: GET /api/calculate-discount/?items=0")
    try:
        resp = client.get("/api/calculate-discount/?discount=100&items=0")
        print(f"Server returned status code: {resp.status_code}")
    except Exception as e:
        print(f"Client caught: {e}")
    time.sleep(1.5)

    # 4. AttributeError Bug
    print("\n👉 [TEST 4] Triggering Bug 3: GET /api/user-profile/?user_id=ghost_user")
    try:
        resp = client.get("/api/user-profile/?user_id=ghost_user")
        print(f"Server returned status code: {resp.status_code}")
    except Exception as e:
        print(f"Client caught: {e}")
    time.sleep(1.5)

    # 5. Logger Error
    print("\n👉 [TEST 5] Triggering Bug 4: GET /api/manual-error/ (Direct logger.error)")
    try:
        resp = client.get("/api/manual-error/")
        print(f"Server returned status code: {resp.status_code}")
    except Exception as e:
        print(f"Client caught: {e}")
    time.sleep(1.5)

    print("\n" + "=" * 80)
    print("✅ SIMULATION COMPLETE: All error interception and agent workflows executed!")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()

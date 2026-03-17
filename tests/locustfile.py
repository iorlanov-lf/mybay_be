"""
Load test for POST /ebay/items — Story 5.3 scalability verification.

Pass criteria (NFR-01): p95 response time < 2000ms at 100 concurrent users.

Requirements:
    pip install -r dev-requirements.txt

Usage (headless, against prod):
    API_BYPASS_KEY=<key> locust -f tests/locustfile.py \\
        --host https://ulaptop-be-332375683599.us-east4.run.app \\
        --users 100 --spawn-rate 10 --run-time 2m --headless

Usage (web UI, for interactive exploration):
    API_BYPASS_KEY=<key> locust -f tests/locustfile.py \\
        --host https://ulaptop-be-332375683599.us-east4.run.app

This file has no test_ functions and is not collected by pytest.
"""

import os

from locust import HttpUser, between, events, task

P95_THRESHOLD_MS = 2000

# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

_PAYLOAD_FIRST_PAGE = {
    "name": "MacBookPro",
    "skip": 0,
    "limit": 10,
    "filter": {
        "productLine": ["MacBook Pro"],
        "subject": ["L"],
        "minPrice": 1,
        "maxPrice": 3000,
    },
    "sortSpecs": [{"field": "price", "direction": 1}],
}

_PAYLOAD_SECOND_PAGE = {
    "name": "MacBookPro",
    "skip": 0,
    "limit": 10,
    "filter": {
        "productLine": ["MacBook Pro"],
        "subject": ["L"],
        "ramSize": [16],
        "cpuFamily": ["i7"],
        "ssdSize": [512],
        "minPrice": 1,
        "maxPrice": 3000,
    },
    "sortSpecs": [{"field": "price", "direction": 1}],
}


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class EbayItemsUser(HttpUser):
    """Simulates a user browsing MacBook Pro listings."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        api_key = os.environ.get("API_BYPASS_KEY", "")
        if not api_key:
            raise RuntimeError(
                "API_BYPASS_KEY env var is not set. "
                "Export it before running: export API_BYPASS_KEY=<key>"
            )
        self.client.headers.update({"X-Api-Key": api_key})

    @task(3)
    def search_page1(self) -> None:
        """75%: price filter, page 1."""
        self.client.post(
            "/ebay/items",
            json=_PAYLOAD_FIRST_PAGE,
            name="/ebay/items [page 1]",
        )

    @task(1)
    def search_page2_ram_filter(self) -> None:
        """25%: RAM + price filter, page 2 (skip 10)."""
        self.client.post(
            "/ebay/items",
            json=_PAYLOAD_SECOND_PAGE,
            name="/ebay/items [page 2, ram filter]",
        )


# ---------------------------------------------------------------------------
# Pass/fail hook — exits with code 1 if p95 exceeds threshold
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def check_p95(environment, **_kwargs) -> None:
    stats = environment.runner.stats.total
    p95 = stats.get_response_time_percentile(0.95)

    print("\n── Load Test Summary ──────────────────────────────")
    print(f"  Requests  : {stats.num_requests}")
    print(f"  Failures  : {stats.num_failures}")
    print(f"  p50       : {stats.get_response_time_percentile(0.50):.0f} ms")
    print(f"  p95       : {p95:.0f} ms  (threshold: {P95_THRESHOLD_MS} ms)")
    print(f"  p99       : {stats.get_response_time_percentile(0.99):.0f} ms")
    print("────────────────────────────────────────────────────")

    if p95 > P95_THRESHOLD_MS:
        print(f"  FAIL: p95 {p95:.0f}ms exceeds {P95_THRESHOLD_MS}ms threshold")
        environment.process_exit_code = 1
    else:
        print(f"  PASS: p95 {p95:.0f}ms is within threshold")
        environment.process_exit_code = 0

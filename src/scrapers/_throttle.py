"""Inter-request cooldown helper for scrapers.

Several JM real-estate sites (and realtor.com international) silently rate-
limit when paginated requests fire too close together — the response stays
HTTP 200 but content is empty, which our break-on-empty pagination logic
then mistakes for "no more listings" and stops early. A small mandatory
gap between requests on the same session avoids this without slowing the
overall daily run materially (8 scrapers × ~10 pages × 0.4s ≈ 30s extra).

Usage:
    throttle = Throttle()
    with cf.Session(impersonate="chrome131") as s:
        r = polite_get(s, url, throttle, timeout=30)
"""
from __future__ import annotations

import time

DEFAULT_INTERVAL_SEC = 0.4


class Throttle:
    """Enforces a minimum interval between calls. Per-instance, so each
    scraper has its own pacing — global throttling isn't needed since
    different scrapers hit different hosts."""

    def __init__(self, interval_sec: float = DEFAULT_INTERVAL_SEC) -> None:
        self.interval = interval_sec
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if self._last and elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last = time.monotonic()


def polite_get(session, url, throttle: Throttle, **kwargs):
    """Drop-in replacement for `session.get(url, **kwargs)` that waits the
    throttle interval first."""
    throttle.wait()
    return session.get(url, **kwargs)

"""Canonical listing-availability status.

The core accuracy problem for this tracker: Jamaican real-estate sites rarely
remove a listing when it sells, so "still on the page" is a weak signal for
"still for sale". The strongest correction is the site's OWN status label —
many sites relabel a listing Sold / Under Offer / Under Contract (or, on keez,
let the posting Expire) while leaving the page up. This module maps the messy
per-source badge/status text onto a small canonical vocabulary so the rest of
the pipeline can reason about availability uniformly.

Canonical values:
    None          unknown — source exposes no status (treat as available)
    "active"      explicitly for sale / available
    "under_offer" deal in progress (under offer / under contract / pending /
                  reserved) — not freely available, but may still fall through
    "sold"        sold
    "expired"     listing/posting lapsed (keez 'expired')

`is_available` is the single predicate the classifier uses: only unknown and
"active" count as available; everything else routes to the 'unavailable'
bucket regardless of age.
"""
from __future__ import annotations

# Canonical statuses that mean "not freely available right now".
UNAVAILABLE_STATUSES = ("under_offer", "sold", "expired")

# Human labels for the digest.
STATUS_LABELS = {
    "active": "Active",
    "under_offer": "Under offer",
    "sold": "Sold",
    "expired": "Expired",
}


def normalize_status(raw: str | None) -> str | None:
    """Map a source's free-text status/badge onto the canonical vocabulary.
    Returns None when the text carries no recognizable availability signal
    (caller should treat None as 'available, just unlabelled')."""
    if not raw:
        return None
    t = raw.strip().lower()
    if not t:
        return None
    # Order matters: check the unavailable signals before the generic
    # "for sale" ones, since a card can carry both a type and a status badge.
    if "sold" in t:
        return "sold"
    if (
        "under offer" in t
        or "under contract" in t
        or "under negotiation" in t
        or "pending" in t
        or "reserved" in t
    ):
        return "under_offer"
    if "expire" in t:  # 'expired' / 'expires'
        return "expired"
    if (
        "active" in t
        or "available" in t
        or "for sale" in t
        or t == "sale"
        or "new" in t
        or "price" in t  # 'price drop', 'reduced price'
    ):
        return "active"
    return None


def is_available(status: str | None) -> bool:
    """True when a listing should be treated as genuinely for sale. Unknown
    (None) and 'active' are available; sold/under_offer/expired are not."""
    return status is None or status == "active"


def merge_status(a: str | None, b: str | None) -> str | None:
    """Combine the status from two merged source-rows for the same property.
    Bias toward the more cautionary (less available) signal so a 'sold' on one
    source isn't masked by a stale 'active' on another. Precedence:
    sold > under_offer > expired > active > unknown."""
    precedence = {"sold": 4, "under_offer": 3, "expired": 2, "active": 1, None: 0}
    return a if precedence.get(a, 0) >= precedence.get(b, 0) else b

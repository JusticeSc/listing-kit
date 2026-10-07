"""External model provider adapters for Product V1."""
from __future__ import annotations


# Upstream provider codes that mean "the account is in arrears", not a content
# problem. DashScope reports these as HTTP 400 with code=Arrearage; nothing can
# succeed until the operator recharges, so the product must say that plainly.
ARREARS_PROVIDER_CODES = frozenset({"arrearage", "arrears", "overdue"})


def is_arrears_provider_code(value: object) -> bool:
    """True when an upstream provider code says the account is in arrears."""
    return isinstance(value, str) and value.strip().lower() in ARREARS_PROVIDER_CODES

"""Request authentication and tenant resolution (enforced in code, before any handler runs).

- No tokens configured (local single-user mode): every request is the admin of tenant "default".
- ADMIN_TOKEN: admin of tenant "default" (also allowed: simulation lab, kill switch).
- TENANT_TOKENS="acme:tok1,beta:tok2": members, each confined to their own tenant's data and the
  real-data endpoints only.
Once any token is configured, EVERY /api request (reads included) needs a valid X-Tahsila-Token.
"""

from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass

from ..ledger.store import DEFAULT_TENANT

MEMBER_PREFIXES = ("/api/status", "/api/audit", "/api/investigations", "/api/memory", "/api/profit/", "/api/guide/")
_TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


@dataclass(frozen=True)
class Principal:
    tenant: str
    role: str  # admin | member
    authenticated: bool


def _tokens() -> list[tuple[str, str, str]]:
    out = []
    admin = os.environ.get("ADMIN_TOKEN", "").strip()
    if admin:
        out.append((admin, DEFAULT_TENANT, "admin"))
    for item in os.environ.get("TENANT_TOKENS", "").split(","):
        tenant, _, token = item.strip().partition(":")
        tenant, token = tenant.strip().lower(), token.strip()
        if token and len(token) >= 12 and _TENANT_ID.match(tenant):
            out.append((token, tenant, "member"))
    return out


def auth_configured() -> bool:
    return bool(_tokens())


def resolve(token_header: str | None) -> Principal | None:
    """Principal for a token, or None when tokens are configured and this one is not valid."""
    tokens = _tokens()
    if not tokens:
        return Principal(DEFAULT_TENANT, "admin", authenticated=False)
    given = (token_header or "").encode()
    match = None
    for token, tenant, role in tokens:  # compare against all tokens: no early exit timing signal
        if hmac.compare_digest(given, token.encode()):
            match = Principal(tenant, role, authenticated=True)
    return match


def allowed(principal: Principal, path: str) -> bool:
    return principal.role == "admin" or path.startswith(MEMBER_PREFIXES)

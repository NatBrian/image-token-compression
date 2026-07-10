"""Shared ChatGPT OAuth-refresh plumbing for the OpenAI-subscription relays.

Both the opencode relay (flat `openai` credential shape) and the codex relay
(nested `tokens` shape) refresh against the SAME endpoint with the SAME client
id, and both must serialize concurrent 401-driven refreshes through one process
lock so two racing requests don't each burn the single-use refresh token.

This module owns only those invariants -- the endpoint, the client id, the lock,
and the bare refresh POST. Each CLI module keeps its own credential-file read and
write-back, because those shapes differ.
"""
from __future__ import annotations

import httpx

_OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # from opencode binary
_OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"

_REFRESH_LOCK = None  # asyncio.Lock, initialized lazily (avoids import-time loop binding)


def get_refresh_lock():
    """Return the process-wide refresh lock, creating it on first use.

    Lazy so it binds to the running event loop rather than import time; shared
    across opencode + codex so a burst of 401s serializes into one refresh."""
    global _REFRESH_LOCK
    if _REFRESH_LOCK is None:
        import asyncio
        _REFRESH_LOCK = asyncio.Lock()
    return _REFRESH_LOCK


async def post_refresh(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a fresh token set. Returns the parsed JSON
    body (access_token / refresh_token / expires_in / id_token) or None on any
    failure. Does no disk I/O -- callers persist to their own credential file."""
    if not refresh_token:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _OPENAI_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": _OPENAI_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception:
        return None

"""Transparent OpenAI-compatible proxy.

Intercepts POST .../chat/completions, renders bulky text context to images via
`transform_request`, forwards to the real upstream, and streams the response
back to the client untouched. Every other path/method is a byte-for-byte
passthrough. Fail-open: any error forwards the original request.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .config import Settings, load_settings
from .transform import transform_request
from .anthropic import transform_anthropic_request

_HOP_BY_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "upgrade",
    "accept-encoding",
    "te",
    "trailer",
}
_RESP_STRIP = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive"}


def _is_messages_path(path: str) -> bool:
    return path.rstrip("/").endswith("/v1/messages")


def _upstream_url(path: str, settings: Settings) -> str:
    # Anthropic-native Messages endpoint: forward verbatim to the Anthropic base.
    if _is_messages_path(path):
        return settings.anthropic_upstream_base + path
    base = settings.upstream_base
    # Recommended client baseURL is http://host:port/v1 -> strip the leading /v1
    # because upstream_base already carries the provider's version segment.
    if path.startswith("/v1/"):
        return base + path[len("/v1"):]
    if path == "/v1":
        return base
    return base + path


def _is_chat_path(path: str) -> bool:
    return path.endswith("/chat/completions")


def _read_oauth_token(settings: Settings) -> str | None:
    """Read Claude Code's subscription OAuth access token at forward time so token
    refreshes are picked up. Returns None if unavailable."""
    try:
        d = json.loads(Path(settings.anthropic_credentials_path).expanduser().read_text())
        tok = d.get("claudeAiOauth", {}).get("accessToken")
        return tok if isinstance(tok, str) and tok else None
    except Exception:
        return None


def _client_headers(request: Request, settings: Settings, is_anthropic: bool = False) -> dict:
    headers = {}
    for k, v in request.headers.items():
        if k.lower() in _HOP_BY_HOP:
            continue
        headers[k] = v
    if is_anthropic:
        # Claude Code strips its subscription credential from non-canonical hosts.
        # Re-inject the locally stored OAuth bearer so api.anthropic.com accepts it.
        if settings.anthropic_oauth_inject and not any(
            h in {k.lower() for k in headers} for h in ("authorization", "x-api-key")
        ):
            tok = _read_oauth_token(settings)
            if tok:
                headers["authorization"] = f"Bearer {tok}"
                headers.pop("x-api-key", None)
        return headers
    if settings.upstream_key:
        headers["authorization"] = f"Bearer {settings.upstream_key}"
    return headers


_SECRET_HEADERS = {"authorization", "x-api-key", "cookie", "proxy-authorization"}


def _redact_headers(headers) -> dict:
    """Header dict safe to persist to disk: never write a live API key/token."""
    return {k: ("<redacted>" if k.lower() in _SECRET_HEADERS else v)
            for k, v in headers.items()}


def _resp_headers(upstream: httpx.Response) -> dict:
    return {k: v for k, v in upstream.headers.items() if k.lower() not in _RESP_STRIP}


def _log_event(settings: Settings, event: dict) -> None:
    if not settings.log_events:
        return
    try:
        p = Path(settings.log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def _capture(settings: Settings, name: str, data: bytes) -> None:
    if not settings.capture_dir:
        return
    try:
        d = Path(settings.capture_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
    except Exception:
        pass


def build_app(settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> Starlette:
    settings = settings or load_settings()
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout))

    async def handle(request: Request) -> Response:
        path = request.url.path
        raw = await request.body()
        method = request.method
        t0 = time.time()

        # Transform chat-completions (OpenAI) and messages (Anthropic) POSTs;
        # everything else passes through byte-for-byte.
        is_anthropic = _is_messages_path(path)
        transform_this = method == "POST" and (_is_chat_path(path) or is_anthropic)
        out_body = raw
        stats = None

        # Capture every request (not just the ones we transform) so the persistent
        # log always has the untouched original, regardless of path/method.
        _capture(settings, f"req_{int(t0*1000)}_in.json", raw)
        _capture(settings, f"req_{int(t0*1000)}_in_headers.json",
                 json.dumps(_redact_headers(request.headers)).encode("utf-8"))

        if transform_this:
            try:
                body = json.loads(raw)
                if is_anthropic:
                    new_body, stats = transform_anthropic_request(body, settings)
                else:
                    new_body, stats = transform_request(body, settings)
                if stats.compressed:
                    out_body = json.dumps(new_body).encode("utf-8")
                _capture(settings, f"req_{int(t0*1000)}_out.json", out_body)
            except Exception as e:
                stats = None
                out_body = raw  # fail-open

        url = _upstream_url(path, settings) + (("?" + request.url.query) if request.url.query else "")
        headers = _client_headers(request, settings, is_anthropic=is_anthropic)

        try:
            upstream_req = client.build_request(method, url, headers=headers, content=out_body)
            upstream = await client.send(upstream_req, stream=True)
        except Exception as e:
            _log_event(settings, {"path": path, "error": f"upstream:{type(e).__name__}:{e}"})
            return JSONResponse({"error": f"imgctx upstream error: {e}"}, status_code=502)

        # Tee response text for usage logging without blocking the client stream.
        # Keep the HEAD (non-stream usage / message_start) and a rolling TAIL (the
        # terminal message_delta carrying final output_tokens) so a long stream can't
        # push the authoritative usage out of the buffer.
        head = bytearray()
        tail = bytearray()
        max_head = 1_000_000
        max_tail = 256_000

        async def body_iter():
            try:
                # aiter_bytes yields DECOMPRESSED bytes (httpx auto-negotiates gzip).
                # We strip content-encoding/length from the response headers, so the
                # client must receive identity-coded bytes, not the raw compressed ones.
                async for chunk in upstream.aiter_bytes():
                    if len(head) < max_head:
                        head.extend(chunk[: max_head - len(head)])
                    tail.extend(chunk)
                    if len(tail) > max_tail:
                        del tail[:-max_tail]
                    yield chunk
            finally:
                await upstream.aclose()
                _finalize()

        def _finalize():
            collected = bytes(head) + (b"\n" + bytes(tail) if tail else b"")
            usage = (_parse_usage_anthropic(collected) if is_anthropic
                     else _parse_usage(collected))
            event = {
                "ts": t0,
                "path": path,
                "status": upstream.status_code,
                "duration_ms": round((time.time() - t0) * 1000, 1),
                "model": (stats.model if stats else None),
            }
            if stats is not None:
                event["transform"] = stats.to_dict()
            if usage is not None:
                event["usage"] = usage
            # Always persist the untouched response bytes + headers to disk. Our own
            # usage/cost parsing is best-effort and provider response shapes vary (a
            # paid endpoint's cost field may live somewhere _parse_usage doesn't look);
            # without this, a parsing gap on a paid run is unrecoverable except by
            # re-running (and re-billing). Capped per-call so this can't grow unbounded.
            tag = f"resp_{int(t0 * 1000)}"
            _capture(settings, f"{tag}.json", collected[:2_000_000])
            _capture(settings, f"{tag}_headers.json",
                     json.dumps(dict(upstream.headers)).encode("utf-8"))
            _log_event(settings, event)

        return StreamingResponse(
            body_iter(),
            status_code=upstream.status_code,
            headers=_resp_headers(upstream),
            media_type=upstream.headers.get("content-type"),
        )

    routes = [Route("/{path:path}", handle, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])]
    app = Starlette(routes=routes)
    app.state.settings = settings
    return app


def _parse_usage(data: bytes) -> dict | None:
    """Best-effort usage extraction from a JSON or SSE response body."""
    if not data:
        return None
    text = data.decode("utf-8", errors="ignore")
    # SSE: scan for the last data: line carrying a usage object.
    if "data:" in text:
        usage = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]" or not payload:
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("usage"):
                usage = obj["usage"]
        return usage
    # Plain JSON.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj.get("usage")
    except Exception:
        return None
    return None


def _parse_usage_anthropic(data: bytes) -> dict | None:
    """Merge Anthropic usage across the response.

    Non-stream: `usage` carries input/output/cache tokens together.
    Stream: `message_start` carries input + cache tokens (output_tokens is a stub);
    `message_delta` carries the final output_tokens. So we take input/cache from the
    first usage that reports input_tokens and output from the last usage seen."""
    if not data:
        return None
    text = data.decode("utf-8", errors="ignore")
    # Try a plain JSON body first (a non-stream response may legitimately contain the
    # substring "data:" in the model's text, so don't branch on that substring).
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and isinstance(obj.get("usage"), dict):
                return obj["usage"]
        except Exception:
            pass
    merged: dict = {}
    last_output = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        usage = obj.get("usage")
        if not usage and isinstance(obj.get("message"), dict):
            usage = obj["message"].get("usage")
        if not isinstance(usage, dict):
            continue
        if usage.get("input_tokens") is not None and "input_tokens" not in merged:
            for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                if usage.get(k) is not None:
                    merged[k] = usage[k]
        if usage.get("output_tokens") is not None:
            last_output = usage["output_tokens"]
    if last_output is not None:
        merged["output_tokens"] = last_output
    return merged or None

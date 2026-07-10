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
from .anthropic import (
    transform_anthropic_request,
    read_oauth_token as read_anthropic_token,
    parse_usage as parse_usage_anthropic,
)
from .codex import (
    transform_responses_native,
    read_oauth_token as read_codex_token,
    refresh_token as refresh_codex_token,
)
from .opencode import (
    chat_completions_to_responses,
    make_sse_converter,
    transform_responses_request,
    read_oauth_token as read_openai_token,
    refresh_token as refresh_openai_token,
)

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
    # Codex CLI relay: the client already speaks the Responses API, so route its
    # /responses call to the ChatGPT codex backend and forward everything else to the
    # same base + path (Codex only ever hits /responses in this mode).
    if settings.codex_oauth:
        base = settings.openai_oauth_upstream_base.rstrip("/")
        if _is_responses_path(path):
            return base + "/responses"
        return base + path

    # NEW: OpenAI OAuth mode: ALL paths route to /responses
    if settings.openai_oauth:
        return settings.openai_oauth_upstream_base.rstrip("/") + "/responses"

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
    return path.rstrip("/").endswith("/chat/completions")


def _is_responses_path(path: str) -> bool:
    # Match both /v1/responses (baseURL .../v1) and a bare /responses (baseURL host:port).
    return path.rstrip("/").endswith("/responses")


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
            tok = read_anthropic_token(settings)
            if tok:
                headers["authorization"] = f"Bearer {tok}"
                headers.pop("x-api-key", None)
        return headers

    # Codex CLI relay: inject the ChatGPT OAuth bearer + account id from Codex's
    # auth.json, overriding whatever the CLI attached (a dummy env_key, or nothing).
    # This keeps the relay working regardless of how Codex authenticates a custom
    # provider, and never depends on it sending its subscription token to localhost.
    if settings.codex_oauth:
        tokens = read_codex_token(settings)
        if tokens:
            headers["authorization"] = f"Bearer {tokens['access']}"
            headers["ChatGPT-Account-Id"] = tokens["account_id"]
            headers.pop("x-api-key", None)
        return headers

    # NEW: OpenAI OAuth relay: inject tokens from opencode's auth.json
    if settings.openai_oauth:
        tokens = read_openai_token(settings)
        if tokens:
            headers["authorization"] = f"Bearer {tokens['access']}"
            headers["ChatGPT-Account-Id"] = tokens["account_id"]
            # Remove any client-supplied auth header (we use ours)
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
        is_responses = _is_responses_path(path)
        transform_this = method == "POST" and (_is_chat_path(path) or is_responses or is_anthropic)
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
                elif is_responses:
                    # Codex speaks native Responses: image the input in place (lossless
                    # for tool/reasoning items). The opencode path uses the round-trip.
                    if settings.codex_oauth:
                        new_body, stats = transform_responses_native(body, settings)
                    else:
                        new_body, stats = transform_responses_request(body, settings)
                else:
                    new_body, stats = transform_request(body, settings)
                if stats.compressed:
                    out_body = json.dumps(new_body).encode("utf-8")
            except Exception:
                stats = None
                out_body = raw  # fail-open

        url = _upstream_url(path, settings) + (("?" + request.url.query) if request.url.query else "")
        headers = _client_headers(request, settings, is_anthropic=is_anthropic)

        # OpenAI OAuth (codex) mode: the chatgpt.com /responses endpoint speaks the
        # Responses API and wants store:false + stream:true. Convert Chat Completions
        # bodies (opencode's @ai-sdk/openai-compatible path) into Responses format; a
        # body that is ALREADY Responses (has "input", e.g. transform_responses_request
        # ran) is only flagged, never re-converted.
        if settings.openai_oauth and method == "POST":
            try:
                body_dict = json.loads(out_body)
                body_dict["stream"] = True
                body_dict["store"] = False
                if "messages" in body_dict:
                    body_dict = chat_completions_to_responses(body_dict)
                out_body = json.dumps(body_dict).encode("utf-8")
            except Exception:
                pass

        # Persist the EXACT bytes we send upstream (post-compression, post-OAuth
        # conversion) so a failed extraction never forces a paid rerun; the raw
        # request on disk always matches what the provider actually billed.
        if method == "POST" and (transform_this or settings.openai_oauth):
            _capture(settings, f"req_{int(t0*1000)}_out.json", out_body)

        try:
            upstream_req = client.build_request(method, url, headers=headers, content=out_body)
            upstream = await client.send(upstream_req, stream=True)
        except Exception as e:
            _log_event(settings, {"path": path, "error": f"upstream:{type(e).__name__}:{e}"})
            return JSONResponse({"error": f"imgctx upstream error: {e}"}, status_code=502)

        # On 401 in a ChatGPT-OAuth relay mode, refresh the token and retry once.
        if upstream.status_code == 401 and (settings.openai_oauth or settings.codex_oauth):
            await upstream.aclose()
            new_tokens = (await refresh_codex_token(settings) if settings.codex_oauth
                          else await refresh_openai_token(settings))
            if new_tokens:
                headers["authorization"] = f"Bearer {new_tokens['access']}"
                headers["ChatGPT-Account-Id"] = new_tokens["account_id"]
                try:
                    upstream_req = client.build_request(method, url, headers=headers, content=out_body)
                    upstream = await client.send(upstream_req, stream=True)
                except Exception as e:
                    _log_event(settings, {"path": path, "error": f"retry:{type(e).__name__}:{e}"})
                    return JSONResponse({"error": f"imgctx upstream retry error: {e}"}, status_code=502)
            else:
                return JSONResponse({"error": "OAuth token refresh failed"}, status_code=502)

        # Tee response text for usage logging without blocking the client stream.
        # Keep the HEAD (non-stream usage / message_start) and a rolling TAIL (the
        # terminal message_delta carrying final output_tokens) so a long stream can't
        # push the authoritative usage out of the buffer.
        head = bytearray()
        tail = bytearray()
        max_head = 1_000_000
        max_tail = 256_000
        resp_tag = f"resp_{int(t0 * 1000)}"
        # Full raw response is streamed to disk chunk-by-chunk (bounded memory, no
        # truncation) so post-hoc debugging never needs a rerun. The head/tail buffers
        # below stay small and exist ONLY for in-memory usage parsing.
        _cap = {"fh": None, "on": bool(settings.capture_dir)}

        def _cap_stream(chunk: bytes) -> None:
            if not _cap["on"]:
                return
            try:
                if _cap["fh"] is None:
                    d = Path(settings.capture_dir)
                    d.mkdir(parents=True, exist_ok=True)
                    _cap["fh"] = (d / f"{resp_tag}.json").open("wb")
                _cap["fh"].write(chunk)
            except Exception:
                _cap["on"] = False  # disable on any I/O error; never break the stream

        async def body_iter():
            _convert = make_sse_converter()
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
                    _cap_stream(chunk)  # full raw upstream bytes (pre-conversion)
                    # Convert Responses API SSE to Chat Completions SSE for OpenAI OAuth mode
                    if settings.openai_oauth:
                        converted = _convert(chunk)
                        if converted:
                            yield converted
                    else:
                        yield chunk
            finally:
                await upstream.aclose()
                if _cap["fh"] is not None:
                    try:
                        _cap["fh"].close()
                    except Exception:
                        pass
                _finalize()

        def _finalize():
            collected = bytes(head) + (b"\n" + bytes(tail) if tail else b"")
            usage = (parse_usage_anthropic(collected) if is_anthropic
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
            # The full raw response body was already streamed to {resp_tag}.json above.
            # Here we persist the response headers alongside it and log the event. Both
            # are best-effort; the on-disk raw body is the source of truth for a paid run
            # so a usage/cost parse gap never forces a rerun (and re-billing).
            _capture(settings, f"{resp_tag}_headers.json",
                     json.dumps(dict(upstream.headers)).encode("utf-8"))
            _log_event(settings, event)

        return StreamingResponse(
            body_iter(),
            status_code=upstream.status_code,
            headers=_resp_headers(upstream),
            media_type="text/event-stream" if settings.openai_oauth else upstream.headers.get("content-type"),
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
            if isinstance(obj, dict):
                u = obj.get("usage")
                if u is None:
                    u = obj.get("response", {}).get("usage")
                if u:
                    usage = u
        return usage
    # Plain JSON.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            u = obj.get("usage")
            if u is None:
                u = obj.get("response", {}).get("usage")
            return u
    except Exception:
        return None
    return None

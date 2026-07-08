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


def _upstream_url(path: str, settings: Settings) -> str:
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


def _client_headers(request: Request, settings: Settings) -> dict:
    headers = {}
    for k, v in request.headers.items():
        if k.lower() in _HOP_BY_HOP:
            continue
        headers[k] = v
    if settings.upstream_key:
        headers["authorization"] = f"Bearer {settings.upstream_key}"
    return headers


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

        # Only transform chat completions POSTs; everything else passes through.
        transform_this = method == "POST" and _is_chat_path(path)
        out_body = raw
        stats = None

        if transform_this:
            _capture(settings, f"req_{int(t0*1000)}_in.json", raw)
            try:
                body = json.loads(raw)
                new_body, stats = transform_request(body, settings)
                if stats.compressed:
                    out_body = json.dumps(new_body).encode("utf-8")
                _capture(settings, f"req_{int(t0*1000)}_out.json", out_body)
            except Exception as e:
                stats = None
                out_body = raw  # fail-open

        url = _upstream_url(path, settings) + (("?" + request.url.query) if request.url.query else "")
        headers = _client_headers(request, settings)

        try:
            upstream_req = client.build_request(method, url, headers=headers, content=out_body)
            upstream = await client.send(upstream_req, stream=True)
        except Exception as e:
            _log_event(settings, {"path": path, "error": f"upstream:{type(e).__name__}:{e}"})
            return JSONResponse({"error": f"imgctx upstream error: {e}"}, status_code=502)

        # Tee response text for usage logging without blocking the client stream.
        collected = bytearray()
        max_collect = 2_000_000

        async def body_iter():
            try:
                async for chunk in upstream.aiter_raw():
                    if len(collected) < max_collect:
                        collected.extend(chunk[: max_collect - len(collected)])
                    yield chunk
            finally:
                await upstream.aclose()
                _finalize()

        def _finalize():
            usage = _parse_usage(bytes(collected))
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

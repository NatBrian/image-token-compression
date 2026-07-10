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
from .transform import transform_request, transform_responses_request
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
    # NEW: OpenAI OAuth mode — ALL paths route to /responses
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
    return path.rstrip("/").endswith("/v1/responses")


# Chat-Completions-only params the codex Responses endpoint rejects or ignores.
_RESP_DROP_PARAMS = (
    "temperature", "top_p", "n", "presence_penalty", "frequency_penalty",
    "logit_bias", "user", "stop", "logprobs", "top_logprobs", "response_format",
    "seed", "service_tier", "verbosity", "max_tokens", "max_completion_tokens",
    "max_output_tokens", "stream_options", "modalities", "audio", "prediction",
)


def _flatten_text(content) -> str:
    """Collapse a Chat message content (str or part list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text"):
                out.append(p.get("text", ""))
            elif isinstance(p, str):
                out.append(p)
        return "\n".join(out)
    return ""


def _content_parts_to_responses(content, assistant: bool) -> list:
    """Chat content parts -> Responses content parts. Model-authored (assistant)
    text is `output_text`; everything else is `input_text`. Image parts (including
    imgctx's compressed data-URL images) become `input_image` regardless of role."""
    text_type = "output_text" if assistant else "input_text"
    if isinstance(content, str):
        return [{"type": text_type, "text": content}] if content else []
    if not isinstance(content, list):
        return []
    parts = []
    for p in content:
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t in ("text", "input_text", "output_text"):
            parts.append({"type": text_type, "text": p.get("text", "")})
        elif t == "image_url":
            url = p.get("image_url")
            url = url.get("url", "") if isinstance(url, dict) else (url or "")
            parts.append({"type": "input_image", "image_url": url})
        else:
            parts.append(p)  # already-Responses-shaped or unknown; passthrough
    return parts


def _convert_tools_to_responses(tools) -> list:
    """Chat function tools `{type:function, function:{name,...}}` -> Responses
    flat function tools `{type:function, name, ...}`."""
    out = []
    for t in tools or []:
        if isinstance(t, dict) and t.get("type") == "function" and isinstance(t.get("function"), dict):
            fn = t["function"]
            rt = {"type": "function", "name": fn.get("name", ""),
                  "parameters": fn.get("parameters") or {"type": "object", "properties": {}}}
            if fn.get("description"):
                rt["description"] = fn["description"]
            out.append(rt)
        else:
            out.append(t)  # already flat / non-function; passthrough
    return out


def _convert_tool_choice(tc):
    """Chat tool_choice -> Responses tool_choice ('auto'/'none'/'required' pass
    through; a specific function ref is flattened)."""
    if isinstance(tc, dict) and tc.get("type") == "function":
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name")
        if name:
            return {"type": "function", "name": name}
    return tc


def _chat_completions_to_responses(body: dict) -> dict:
    """Convert an OpenAI Chat Completions request into the Responses API request the
    chatgpt.com codex backend expects at /responses.

    Unlike a plain text-only bridge this preserves the FULL agent loop: tool
    definitions, tool_choice, prior assistant tool_calls, and tool results are all
    translated, so opencode can actually call tools through the OAuth relay."""
    for key in _RESP_DROP_PARAMS:
        body.pop(key, None)

    # reasoning_effort -> reasoning.effort (the Codex-native shape)
    effort = body.pop("reasoning_effort", None)
    if effort:
        body["reasoning"] = {"effort": effort}

    if isinstance(body.get("tools"), list):
        body["tools"] = _convert_tools_to_responses(body["tools"])
    if "tool_choice" in body:
        body["tool_choice"] = _convert_tool_choice(body["tool_choice"])

    messages = body.pop("messages", None)
    if messages is None:
        return body

    instructions = body.get("instructions", "")
    input_data: list = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role in ("system", "developer"):
            text = _flatten_text(content)
            if text:
                instructions = (text + "\n\n" + instructions) if instructions else text
            continue

        if role == "tool":
            # Chat tool result -> Responses function_call_output
            input_data.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id", ""),
                "output": _flatten_text(content),
            })
            continue

        if role == "assistant":
            parts = _content_parts_to_responses(content, assistant=True)
            if parts:
                input_data.append({"type": "message", "role": "assistant", "content": parts})
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                input_data.append({
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "") or "{}",
                })
            continue

        # user (and any other) role
        input_data.append({
            "type": "message", "role": role,
            "content": _content_parts_to_responses(content, assistant=False),
        })

    body["input"] = input_data
    if instructions:
        body["instructions"] = instructions.strip()
    return body


def _read_oauth_token(settings: Settings) -> str | None:
    """Read Claude Code's subscription OAuth access token at forward time so token
    refreshes are picked up. Returns None if unavailable."""
    try:
        d = json.loads(Path(settings.anthropic_credentials_path).expanduser().read_text())
        tok = d.get("claudeAiOauth", {}).get("accessToken")
        return tok if isinstance(tok, str) and tok else None
    except Exception:
        return None


def _read_openai_oauth_token(settings: Settings) -> dict | None:
    """Read opencode's OpenAI OAuth tokens at forward time.

    Returns {"access": str, "refresh": str, "account_id": str} or None.
    Follows the same pattern as _read_oauth_token() for Anthropic.
    """
    try:
        path = Path(settings.openai_credentials_path).expanduser()
        data = json.loads(path.read_text())
        oa = data.get("openai") or {}
        if oa.get("type") != "oauth":
            return None
        access = oa.get("access", "")
        refresh = oa.get("refresh", "")
        account_id = oa.get("accountId", "")
        if not access or not account_id:
            return None
        return {"access": access, "refresh": refresh, "account_id": account_id}
    except Exception:
        return None


def _make_sse_converter():
    """Factory returning a per-request Responses-SSE -> Chat-Completions-SSE
    converter closure. Handles text deltas AND streaming tool calls
    (response.output_item.added[function_call] + function_call_arguments.delta),
    so opencode's agent loop sees tool calls, not just prose."""
    sent_first = False
    response_id = "chatcmpl-"
    model_name = "gpt-5.4-mini"
    _buf = ""
    tool_idx: dict[str, int] = {}   # Responses item id -> Chat tool_calls index
    next_idx = 0
    has_tool_calls = False

    def frame(delta: dict, finish=None, usage=None) -> str:
        choice = {"index": 0, "delta": delta, "finish_reason": finish}
        obj = {"id": response_id, "object": "chat.completion.chunk",
               "created": int(time.time()), "model": model_name, "choices": [choice]}
        if usage is not None:
            obj["usage"] = usage
        return "data: " + json.dumps(obj)

    def convert(chunk: bytes) -> bytes:
        nonlocal sent_first, response_id, model_name, _buf, next_idx, has_tool_calls
        _buf += chunk.decode("utf-8", errors="replace")
        out_lines = []
        while True:
            idx = _buf.find("\n")
            if idx == -1:
                break
            line = _buf[:idx].strip()
            _buf = _buf[idx + 1:]
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].lstrip()
            if payload == "[DONE]" or not payload:
                continue
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            evt_type = obj.get("type")
            if evt_type == "response.created":
                resp = obj.get("response", {}) or {}
                response_id = resp.get("id", response_id)
                model_name = resp.get("model", model_name)

            elif evt_type == "response.output_item.added":
                item = obj.get("item", {}) or {}
                if item.get("type") == "function_call":
                    has_tool_calls = True
                    iid = item.get("id", "")
                    tool_idx[iid] = next_idx
                    delta = {"tool_calls": [{
                        "index": next_idx,
                        "id": item.get("call_id") or iid,
                        "type": "function",
                        "function": {"name": item.get("name", ""),
                                     "arguments": item.get("arguments", "") or ""},
                    }]}
                    if not sent_first:
                        sent_first = True
                        delta["role"] = "assistant"
                    next_idx += 1
                    out_lines.append(frame(delta))

            elif evt_type == "response.function_call_arguments.delta":
                iid = obj.get("item_id", "")
                d = obj.get("delta", "")
                if d and iid in tool_idx:
                    out_lines.append(frame({"tool_calls": [{
                        "index": tool_idx[iid], "function": {"arguments": d}}]}))

            elif evt_type == "response.output_text.delta":
                d = obj.get("delta", "")
                if d:
                    delta = {"content": d}
                    if not sent_first:
                        sent_first = True
                        delta["role"] = "assistant"
                    out_lines.append(frame(delta))

            elif evt_type == "response.completed":
                resp = obj.get("response", {}) or {}
                response_id = resp.get("id", response_id)
                model_name = resp.get("model", model_name)
                u = resp.get("usage") or {}
                usage = None
                if u:
                    usage = {"prompt_tokens": u.get("input_tokens", 0),
                             "completion_tokens": u.get("output_tokens", 0),
                             "total_tokens": u.get("total_tokens", 0)}
                    itd = u.get("input_tokens_details") or {}
                    if itd.get("cached_tokens") is not None:
                        usage["prompt_tokens_details"] = {"cached_tokens": itd.get("cached_tokens", 0)}
                fin = "tool_calls" if has_tool_calls else "stop"
                out_lines.append(frame({}, finish=fin, usage=usage))
                out_lines.append("data: [DONE]")

            elif evt_type in ("response.failed", "response.error", "error"):
                # Surface the upstream error to the client instead of hanging the stream.
                err = obj.get("response", obj)
                out_lines.append("data: " + json.dumps({"error": err}))
                out_lines.append("data: [DONE]")

        # Each SSE event MUST end with a blank line (\n\n). The AI-SDK eventsource
        # parser concatenates consecutive `data:` lines into ONE event until it sees
        # that blank line -- single-\n framing merges every chunk into an unparseable
        # blob and nothing dispatches (silent: no text, no tool calls).
        return "".join(l + "\n\n" for l in out_lines).encode("utf-8") if out_lines else b""

    return convert


_REFRESH_LOCK = None  # asyncio.Lock, initialized lazily
_OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # from opencode binary
_OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"


async def _refresh_openai_token(settings: Settings) -> dict | None:
    """Refresh the OAuth access token using the refresh token.

    Uses a per-process asyncio lock so concurrent 401s don't race.
    Returns {"access": str, "refresh": str, "account_id": str} or None.
    """
    global _REFRESH_LOCK
    if _REFRESH_LOCK is None:
        import asyncio
        _REFRESH_LOCK = asyncio.Lock()

    async with _REFRESH_LOCK:
        # Re-read tokens (another request may have refreshed already)
        tokens = _read_openai_oauth_token(settings)
        if not tokens or not tokens.get("refresh"):
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _OPENAI_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": tokens["refresh"],
                        "client_id": _OPENAI_CLIENT_ID,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code != 200:
                    return None
                body = resp.json()
        except Exception:
            return None

        new_access = body.get("access_token", "")
        new_refresh = body.get("refresh_token", tokens["refresh"])
        expires_in = body.get("expires_in", 86400)
        if not new_access:
            return None

        # Update auth.json on disk
        try:
            path = Path(settings.openai_credentials_path).expanduser()
            current = json.loads(path.read_text())
            if "openai" in current:
                current["openai"]["access"] = new_access
                current["openai"]["refresh"] = new_refresh
                current["openai"]["expires"] = int(time.time() * 1000) + expires_in * 1000
                path.write_text(json.dumps(current, indent=2))
        except Exception:
            pass  # Non-fatal: next refresh will retry

        return {
            "access": new_access,
            "refresh": new_refresh,
            "account_id": tokens.get("account_id", ""),
        }


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

    # NEW: OpenAI OAuth relay — inject tokens from opencode's auth.json
    if settings.openai_oauth:
        tokens = _read_openai_oauth_token(settings)
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
                    body_dict = _chat_completions_to_responses(body_dict)
                out_body = json.dumps(body_dict).encode("utf-8")
            except Exception:
                pass

        # Persist the EXACT bytes we send upstream (post-compression, post-OAuth
        # conversion) so a failed extraction never forces a paid rerun -- the raw
        # request on disk always matches what the provider actually billed.
        if method == "POST" and (transform_this or settings.openai_oauth):
            _capture(settings, f"req_{int(t0*1000)}_out.json", out_body)

        try:
            upstream_req = client.build_request(method, url, headers=headers, content=out_body)
            upstream = await client.send(upstream_req, stream=True)
        except Exception as e:
            _log_event(settings, {"path": path, "error": f"upstream:{type(e).__name__}:{e}"})
            return JSONResponse({"error": f"imgctx upstream error: {e}"}, status_code=502)

        # On 401 in OpenAI OAuth mode, attempt token refresh and retry once
        if upstream.status_code == 401 and settings.openai_oauth:
            await upstream.aclose()
            new_tokens = await _refresh_openai_token(settings)
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

        async def body_iter():
            _convert = _make_sse_converter()
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
                    # Convert Responses API SSE to Chat Completions SSE for OpenAI OAuth mode
                    if settings.openai_oauth:
                        converted = _convert(chunk)
                        if converted:
                            yield converted
                    else:
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

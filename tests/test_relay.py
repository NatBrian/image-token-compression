"""Relay-path guard tests: opencode (OpenAI OAuth) + codex (native Responses).

These pin the behaviour the two OAuth relays must preserve across the module
split -- routing to /responses, OAuth header injection from each CLI's own
credential file shape, chat->responses conversion (opencode only), and the
SSE handling (opencode converts Responses->Chat; codex passes native through).

They run fully in-process against a fake ChatGPT /responses upstream -- no
network, no paid quota -- so the refactor is CI-guarded instead of validated
only by live runs.
"""
import json

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from imgctx.config import load_settings
from imgctx.proxy import build_app


def make_responses_upstream():
    """Fake chatgpt.com backend: captures the request and streams a minimal
    native Responses SSE (one text delta + completed with usage)."""
    received = {}

    async def responses(request):
        received["body"] = json.loads(await request.body())
        received["auth"] = request.headers.get("authorization")
        received["account"] = request.headers.get("chatgpt-account-id")

        async def gen():
            yield b'data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.4-mini"}}\n\n'
            yield b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
            yield (b'data: {"type":"response.completed","response":{"id":"resp_1",'
                   b'"model":"gpt-5.4-mini","usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12}}}\n\n')
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    app = Starlette(routes=[Route("/responses", responses, methods=["POST"])])
    return app, received


async def _call(app, path, body, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://proxy.local") as c:
        return await c.post(path, json=body, headers=headers)


# --- opencode: OpenAI OAuth relay (Chat Completions in, Responses upstream) ---

@pytest.fixture
def opencode_wired(tmp_path):
    up_app, received = make_responses_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    cred = tmp_path / "opencode_auth.json"
    cred.write_text(json.dumps({"openai": {
        "type": "oauth", "access": "ACCESS_OC", "refresh": "REFRESH_OC", "accountId": "ACCT_OC",
    }}))

    settings = load_settings()
    settings.openai_oauth = True
    settings.openai_credentials_path = str(cred)
    settings.openai_oauth_upstream_base = "http://up.local"
    settings.log_events = False

    app = build_app(settings, client=client)
    return app, received, settings


@pytest.mark.asyncio
async def test_opencode_relay_converts_and_injects(opencode_wired):
    app, received, settings = opencode_wired
    body = {
        "model": "gpt-5.4-mini",
        "messages": [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "hi"},
        ],
        "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
        "tool_choice": "auto",
        "reasoning_effort": "low",
    }
    r = await _call(app, "/v1/chat/completions", body)
    assert r.status_code == 200

    up = received["body"]
    # Chat -> Responses conversion happened.
    assert "input" in up and "messages" not in up
    assert up["stream"] is True and up["store"] is False
    # system folded into instructions; user survives as an input message.
    assert "helper" in up.get("instructions", "")
    assert any(it.get("type") == "message" and it.get("role") == "user" for it in up["input"])
    # tools flattened to Responses shape.
    assert up["tools"][0]["type"] == "function" and up["tools"][0]["name"] == "read"
    # reasoning_effort -> reasoning.effort
    assert up["reasoning"] == {"effort": "low"}
    # OAuth injected from opencode's flat `openai` credential shape.
    assert received["auth"] == "Bearer ACCESS_OC"
    assert received["account"] == "ACCT_OC"

    # Responses SSE converted back to Chat Completions chunks for the client.
    assert "chat.completion.chunk" in r.text
    assert '"content":"ok"' in r.text or '"content": "ok"' in r.text
    assert "[DONE]" in r.text


# --- codex: native Responses relay (Responses in, native passthrough out) ---

@pytest.fixture
def codex_wired(tmp_path):
    up_app, received = make_responses_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    cred = tmp_path / "codex_auth.json"
    cred.write_text(json.dumps({"tokens": {
        "access_token": "ACCESS_CX", "refresh_token": "REFRESH_CX", "account_id": "ACCT_CX",
    }}))

    settings = load_settings()
    settings.codex_oauth = True
    settings.codex_credentials_path = str(cred)
    settings.openai_oauth_upstream_base = "http://up.local"
    settings.log_events = False

    app = build_app(settings, client=client)
    return app, received, settings


@pytest.mark.asyncio
async def test_codex_relay_preserves_native_and_injects(codex_wired):
    app, received, settings = codex_wired
    body = {
        "model": "gpt-5.4-mini",
        "instructions": "system slab",
        "input": [
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "hi"}]},
            {"type": "function_call", "call_id": "c1", "name": "read", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c1", "output": "small result"},
        ],
        "stream": True,
        "store": False,
    }
    r = await _call(app, "/v1/responses", body)
    assert r.status_code == 200

    up = received["body"]
    # Native input preserved in place -- every typed item survives, byte-identical.
    assert up["input"] == body["input"]
    assert up["instructions"] == "system slab"
    # No Chat<->Responses round-trip: no `messages` key ever appears.
    assert "messages" not in up
    # OAuth injected from codex's nested `tokens` credential shape.
    assert received["auth"] == "Bearer ACCESS_CX"
    assert received["account"] == "ACCT_CX"

    # Native Responses SSE passed through untouched (NOT converted to Chat chunks).
    assert "response.output_text.delta" in r.text
    assert "chat.completion.chunk" not in r.text


# --- 401 -> refresh -> retry (the moved refresh_token path, no network) ---

def make_flaky_upstream():
    """Fake backend: 401 on the first hit, 200 (Responses SSE) after. Records the
    Authorization header seen on each call so the retry can be checked."""
    state = {"n": 0, "auth": []}

    async def responses(request):
        state["n"] += 1
        state["auth"].append(request.headers.get("authorization"))
        if state["n"] == 1:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        async def gen():
            yield (b'data: {"type":"response.completed","response":'
                   b'{"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}}\n\n')
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    app = Starlette(routes=[Route("/responses", responses, methods=["POST"])])
    return app, state


async def _fake_refresh_ok(refresh_token):
    # Stand in for the auth.openai.com POST so the test stays offline; the moved
    # refresh_token() wrapper still does the read + disk write-back around it.
    return {"access_token": "NEW_ACCESS", "refresh_token": "NEW_REFRESH",
            "expires_in": 3600, "id_token": "NEW_ID"}


async def _fake_refresh_fail(refresh_token):
    return None


@pytest.mark.asyncio
async def test_codex_401_refreshes_and_retries(tmp_path, monkeypatch):
    up_app, state = make_flaky_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    cred = tmp_path / "codex_auth.json"
    cred.write_text(json.dumps({"tokens": {
        "access_token": "OLD", "refresh_token": "OLD_R", "account_id": "ACCT_CX",
    }}))

    settings = load_settings()
    settings.codex_oauth = True
    settings.codex_credentials_path = str(cred)
    settings.openai_oauth_upstream_base = "http://up.local"
    settings.log_events = False

    # Patch the shared POST as imported into the codex module -> no network.
    monkeypatch.setattr("imgctx.codex.post_refresh", _fake_refresh_ok)

    app = build_app(settings, client=client)
    r = await _call(app, "/v1/responses", {
        "model": "gpt-5.4-mini", "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
    })

    assert r.status_code == 200
    assert state["n"] == 2                        # one 401, one successful retry
    assert state["auth"][0] == "Bearer OLD"       # first try used the stale token
    assert state["auth"][1] == "Bearer NEW_ACCESS"  # retry used the refreshed token
    # Credential file rewritten in codex's nested shape.
    saved = json.loads(cred.read_text())["tokens"]
    assert saved["access_token"] == "NEW_ACCESS"
    assert saved["refresh_token"] == "NEW_REFRESH"
    assert saved["id_token"] == "NEW_ID"


@pytest.mark.asyncio
async def test_opencode_401_refreshes_and_retries(tmp_path, monkeypatch):
    up_app, state = make_flaky_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    cred = tmp_path / "opencode_auth.json"
    cred.write_text(json.dumps({"openai": {
        "type": "oauth", "access": "OLD", "refresh": "OLD_R", "accountId": "ACCT_OC",
    }}))

    settings = load_settings()
    settings.openai_oauth = True
    settings.openai_credentials_path = str(cred)
    settings.openai_oauth_upstream_base = "http://up.local"
    settings.log_events = False

    monkeypatch.setattr("imgctx.opencode.post_refresh", _fake_refresh_ok)

    app = build_app(settings, client=client)
    r = await _call(app, "/v1/chat/completions", {
        "model": "gpt-5.4-mini", "messages": [{"role": "user", "content": "hi"}],
    })

    assert r.status_code == 200
    assert state["n"] == 2
    assert state["auth"][0] == "Bearer OLD"
    assert state["auth"][1] == "Bearer NEW_ACCESS"
    # Credential file rewritten in opencode's flat shape.
    saved = json.loads(cred.read_text())["openai"]
    assert saved["access"] == "NEW_ACCESS"
    assert saved["refresh"] == "NEW_REFRESH"


@pytest.mark.asyncio
async def test_codex_401_refresh_failure_returns_502(tmp_path, monkeypatch):
    up_app, state = make_flaky_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    cred = tmp_path / "codex_auth.json"
    cred.write_text(json.dumps({"tokens": {
        "access_token": "OLD", "refresh_token": "OLD_R", "account_id": "ACCT_CX",
    }}))

    settings = load_settings()
    settings.codex_oauth = True
    settings.codex_credentials_path = str(cred)
    settings.openai_oauth_upstream_base = "http://up.local"
    settings.log_events = False

    monkeypatch.setattr("imgctx.codex.post_refresh", _fake_refresh_fail)

    app = build_app(settings, client=client)
    r = await _call(app, "/v1/responses", {
        "model": "gpt-5.4-mini", "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
    })

    # Refresh failed -> no second upstream hit, explicit 502 (never a hang).
    assert r.status_code == 502
    assert state["n"] == 1
    assert "refresh failed" in r.text.lower()


# --- claude sonnet: Anthropic Messages relay (routing + OAuth inject + usage) ---

def make_anthropic_upstream():
    """Fake api.anthropic.com /v1/messages: records the auth it saw and streams a
    two-part Anthropic SSE (message_start carries input+cache, message_delta the
    final output_tokens) so the merged-usage parse can be checked."""
    received = {}

    async def messages(request):
        received["auth"] = request.headers.get("authorization")
        received["x_api_key"] = request.headers.get("x-api-key")

        async def gen():
            yield (b'event: message_start\ndata: {"type":"message_start","message":'
                   b'{"usage":{"input_tokens":100,"cache_read_input_tokens":10,'
                   b'"cache_creation_input_tokens":5,"output_tokens":1}}}\n\n')
            yield (b'event: message_delta\ndata: {"type":"message_delta",'
                   b'"usage":{"output_tokens":42}}\n\n')
            yield b'event: message_stop\ndata: {"type":"message_stop"}\n\n'

        return StreamingResponse(gen(), media_type="text/event-stream")

    app = Starlette(routes=[Route("/v1/messages", messages, methods=["POST"])])
    return app, received


def _anthropic_settings(tmp_path, cred_body):
    cred = tmp_path / "claude_creds.json"
    cred.write_text(json.dumps(cred_body))
    settings = load_settings()
    settings.anthropic_upstream_base = "http://anthropic.local"
    settings.anthropic_credentials_path = str(cred)
    settings.log_events = False
    return settings


@pytest.mark.asyncio
async def test_anthropic_relay_injects_oauth_and_parses_usage(tmp_path):
    up_app, received = make_anthropic_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    settings = _anthropic_settings(tmp_path, {"claudeAiOauth": {"accessToken": "SUB_TOKEN"}})
    logp = tmp_path / "events.jsonl"
    settings.log_events = True
    settings.log_path = str(logp)

    app = build_app(settings, client=client)
    body = {"model": "claude-sonnet-5", "messages": [{"role": "user", "content": "hi"}]}
    r = await _call(app, "/v1/messages", body)
    assert r.status_code == 200

    # OAuth bearer injected from ~/.claude/.credentials.json (client sent no auth).
    assert received["auth"] == "Bearer SUB_TOKEN"

    # Merged Anthropic usage: input/cache from message_start, output from message_delta.
    ev = [json.loads(l) for l in logp.read_text().splitlines()]
    usage = next(e["usage"] for e in ev if e.get("path", "").endswith("/v1/messages") and "usage" in e)
    assert usage["input_tokens"] == 100
    assert usage["cache_read_input_tokens"] == 10
    assert usage["cache_creation_input_tokens"] == 5
    assert usage["output_tokens"] == 42        # last delta wins, not the message_start stub


@pytest.mark.asyncio
async def test_anthropic_relay_does_not_override_client_auth(tmp_path):
    up_app, received = make_anthropic_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    settings = _anthropic_settings(tmp_path, {"claudeAiOauth": {"accessToken": "SUB_TOKEN"}})
    app = build_app(settings, client=client)
    body = {"model": "claude-sonnet-5", "messages": [{"role": "user", "content": "hi"}]}
    # Client already carries a credential -> the proxy must NOT overwrite it.
    r = await _call(app, "/v1/messages", body, headers={"x-api-key": "CLIENT_KEY"})
    assert r.status_code == 200
    assert received["x_api_key"] == "CLIENT_KEY"
    assert received["auth"] is None            # no injected Bearer over the client's key


# --- opencode builtin (mimo, no OAuth): generic chat path logs usage ---

@pytest.mark.asyncio
async def test_plain_chat_relay_logs_usage(tmp_path):
    """The non-OAuth chat path (opencode's built-in zen/mimo provider) must forward
    untouched and still parse usage from a plain Chat Completions SSE."""
    received = {}

    async def chat(request):
        received["body"] = json.loads(await request.body())

        async def gen():
            yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
            yield b'data: {"usage":{"prompt_tokens":321,"completion_tokens":7}}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    up_app = Starlette(routes=[Route("/zen/v1/chat/completions", chat, methods=["POST"])])
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    settings = load_settings()
    settings.upstream_base = "http://up.local/zen/v1"
    logp = tmp_path / "events.jsonl"
    settings.log_events = True
    settings.log_path = str(logp)

    app = build_app(settings, client=client)
    r = await _call(app, "/v1/chat/completions", {"model": "mimo-v2.5", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "ok" in r.text and "[DONE]" in r.text
    ev = [json.loads(l) for l in logp.read_text().splitlines()]
    usage = next(e["usage"] for e in ev if "usage" in e)
    assert usage["prompt_tokens"] == 321 and usage["completion_tokens"] == 7


# --- dispatch smoke: build_app constructs in every mode (import/wiring guard) ---

def test_build_app_all_four_modes():
    """A pure-construction guard: each relay mode must wire up without ImportError
    or dispatch mis-reference after the module split. No requests sent."""
    base = load_settings()
    base.log_events = False

    mimo = load_settings(); mimo.log_events = False                       # opencode builtin
    anthropic = load_settings(); anthropic.log_events = False             # claude
    openai = load_settings(); openai.log_events = False; openai.openai_oauth = True   # opencode oauth
    codex = load_settings(); codex.log_events = False; codex.codex_oauth = True       # codex

    for s in (mimo, anthropic, openai, codex):
        app = build_app(s)
        assert app is not None


@pytest.mark.asyncio
async def test_capture_writes_full_raw_request_and_response(tmp_path):
    """With IMGCTX_CAPTURE_DIR set, the proxy must persist the raw request body and
    the FULL streamed response body to disk (no truncation) for post-hoc debugging."""
    received = {}
    big_line = '{"choices":[{"delta":{"content":"' + ("x" * 5000) + '"}}]}'

    async def chat(request):
        received["body"] = await request.body()

        async def gen():
            yield ("data: " + big_line + "\n\n").encode()
            yield b'data: {"usage":{"prompt_tokens":5,"completion_tokens":1}}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    up_app = Starlette(routes=[Route("/zen/v1/chat/completions", chat, methods=["POST"])])
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    capdir = tmp_path / "capture"
    settings = load_settings()
    settings.upstream_base = "http://up.local/zen/v1"
    settings.capture_dir = str(capdir)
    settings.log_events = False

    app = build_app(settings, client=client)
    r = await _call(app, "/v1/chat/completions", {"model": "mimo", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200

    files = list(capdir.iterdir())
    req_in = next(f for f in files if "_in.json" in f.name)
    resp = next(f for f in files if f.name.startswith("resp_") and f.name.endswith(".json") and "headers" not in f.name)
    # Raw request preserved.
    assert json.loads(req_in.read_text())["messages"][0]["content"] == "hi"
    # Full response on disk -- the 5000-char delta survived intact (not head/tail clipped).
    body = resp.read_text()
    assert ("x" * 5000) in body
    assert "[DONE]" in body

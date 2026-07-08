"""Proxy tests against an in-process fake upstream (no network)."""
import json

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from imgctx.config import load_settings
from imgctx.proxy import build_app


def make_fake_upstream():
    received = {}

    async def chat(request):
        body = await request.body()
        received["body"] = json.loads(body)
        received["auth"] = request.headers.get("authorization")
        if request.query_params.get("stream") == "1":
            async def gen():
                yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                yield b'data: {"usage":{"prompt_tokens":123,"completion_tokens":2}}\n\n'
                yield b"data: [DONE]\n\n"
            return StreamingResponse(gen(), media_type="text/event-stream")
        return JSONResponse({"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 123}})

    app = Starlette(routes=[Route("/zen/v1/chat/completions", chat, methods=["POST"])])
    return app, received


@pytest.fixture
def wired(tmp_path):
    up_app, received = make_fake_upstream()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up_app), timeout=30)

    settings = load_settings()
    settings.upstream_base = "http://up.local/zen/v1"
    settings.log_events = True
    settings.log_path = str(tmp_path / "events.jsonl")

    app = build_app(settings, client=client)
    return app, received, settings


async def _call(app, path, body, stream=False):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://proxy.local") as c:
        q = "?stream=1" if stream else ""
        return await c.post(path + q, json=body)


@pytest.mark.asyncio
async def test_proxy_forwards_and_compresses(wired):
    app, received, settings = wired
    big = "def f():\n    return 1\n" * 800
    body = {
        "model": "mimo-v2.5-free",
        "messages": [
            {"role": "user", "content": "read"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": big},
        ],
    }
    r = await _call(app, "/v1/chat/completions", body)
    assert r.status_code == 200
    up = received["body"]
    assert any(
        m.get("role") == "user" and isinstance(m.get("content"), list)
        and any(p.get("type") == "image_url" for p in m["content"])
        for m in up["messages"]
    )
    # tool_call_id linkage preserved through the stub.
    tool_msgs = [m for m in up["messages"] if m.get("role") == "tool"]
    assert tool_msgs and tool_msgs[0]["tool_call_id"] == "c1"


@pytest.mark.asyncio
async def test_proxy_passthrough_unsupported_model(wired):
    app, received, settings = wired
    big = "x" * 9000
    body = {"model": "text-only", "messages": [{"role": "user", "content": big}]}
    r = await _call(app, "/v1/chat/completions", body)
    assert r.status_code == 200
    assert received["body"]["messages"][0]["content"] == big


@pytest.mark.asyncio
async def test_proxy_streaming_passthrough(wired):
    app, received, settings = wired
    body = {"model": "mimo", "messages": [{"role": "user", "content": "hi"}]}
    r = await _call(app, "/v1/chat/completions", body, stream=True)
    assert r.status_code == 200
    assert "ok" in r.text and "[DONE]" in r.text

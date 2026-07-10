"""The opencode relay: run opencode's ChatGPT-OAuth path through imgctx.

opencode talks the OpenAI **Chat Completions** wire format (via
`@ai-sdk/openai-compatible`), but a ChatGPT subscription is only reachable at the
codex `/responses` endpoint, which speaks the **Responses** API. So this relay is
a two-way bridge, unlike the codex path (native Responses) or the Anthropic path:

  request  : Chat Completions  --_chat_completions_to_responses-->  Responses
  response : Responses SSE      --_make_sse_converter-->            Chat SSE

`transform_responses_request` is the imaging entry point for the rare case where
opencode is pointed straight at `/responses`; it round-trips through the Chat
imager and back. OAuth read/refresh for opencode's flat `openai` credential shape
also lives here. Shared refresh plumbing (lock, endpoint, POST) comes from _oauth.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import Settings
from ._oauth import get_refresh_lock, post_refresh
from .transform import TransformStats, transform_request


# --- Chat Completions -> Responses request conversion ---

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


def chat_completions_to_responses(body: dict) -> dict:
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


# --- Responses SSE -> Chat Completions SSE conversion ---

def make_sse_converter():
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


# --- OAuth: opencode's flat `openai` credential shape ---

def read_oauth_token(settings: Settings) -> dict | None:
    """Read opencode's OpenAI OAuth tokens at forward time.

    Returns {"access": str, "refresh": str, "account_id": str} or None.
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


async def refresh_token(settings: Settings) -> dict | None:
    """Refresh the OAuth access token using the refresh token.

    Serializes through the shared per-process lock so concurrent 401s don't race.
    Returns {"access": str, "refresh": str, "account_id": str} or None.
    """
    async with get_refresh_lock():
        # Re-read tokens (another request may have refreshed already)
        tokens = read_oauth_token(settings)
        if not tokens or not tokens.get("refresh"):
            return None

        body = await post_refresh(tokens["refresh"])
        if not body:
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


# --- Responses API imaging entry point (opencode -> /responses, round-trip) ---

def _responses_input_to_messages(input_data) -> list[dict]:
    """Convert Responses API input to Chat Completions messages format.

    Responses API input can be:
    - A string (becomes a single user message)
    - An array of {type: "message", role: ..., content: [...]} items
    """
    if isinstance(input_data, str):
        return [{"role": "user", "content": input_data}]
    if not isinstance(input_data, list):
        return []
    messages = []
    for item in input_data:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        role = item.get("role", "user")
        content = item.get("content", "")
        # Convert content format: input_text -> text, input_image -> image_url
        if isinstance(content, list):
            converted = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "input_text":
                    converted.append({"type": "text", "text": part.get("text", "")})
                elif part.get("type") == "input_image":
                    converted.append({
                        "type": "image_url",
                        "image_url": {"url": part.get("image_url", "")},
                    })
                else:
                    converted.append(part)  # passthrough
            messages.append({"role": role, "content": converted})
        else:
            messages.append({"role": role, "content": content})
    return messages


def _messages_to_responses_input(messages: list[dict]) -> list:
    """Convert Chat Completions messages back to Responses API input format.

    Reverse of _responses_input_to_messages.
    """
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Convert content format: text -> input_text, image_url -> input_image
        if isinstance(content, list):
            converted = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    converted.append({"type": "input_text", "text": part.get("text", "")})
                elif part.get("type") == "image_url":
                    converted.append({
                        "type": "input_image",
                        "image_url": part["image_url"]["url"],
                    })
                else:
                    converted.append(part)
            result.append({"type": "message", "role": role, "content": converted})
        else:
            result.append({"type": "message", "role": role, "content": content})
    return result


def transform_responses_request(body: dict, settings: Settings) -> tuple[dict, TransformStats]:
    """Compress a Responses API request body.

    Converts to Chat Completions format, compresses, converts back.
    """
    # Extract instructions as system message
    messages = []
    instructions = body.get("instructions", "")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    # Convert input to messages
    input_data = body.get("input", "")
    input_messages = _responses_input_to_messages(input_data)
    messages.extend(input_messages)

    # Create temporary Chat Completions body
    chat_body = {
        "model": body.get("model"),
        "messages": messages,
        "tools": body.get("tools"),
    }

    # Compress using the existing Chat transformer
    compressed_body, stats = transform_request(chat_body, settings)

    if not stats.compressed:
        return body, stats

    # Convert back to Responses API format
    new_body = dict(body)
    new_messages = compressed_body.get("messages", [])

    # Extract system message back to instructions
    new_instructions = ""
    if new_messages and new_messages[0].get("role") in ("system", "developer"):
        sys_content = new_messages[0].get("content", "")
        if isinstance(sys_content, str):
            new_instructions = sys_content
        new_messages = new_messages[1:]

    if new_instructions:
        new_body["instructions"] = new_instructions
    elif "instructions" in body:
        del new_body["instructions"]

    new_body["input"] = _messages_to_responses_input(new_messages)

    if compressed_body.get("tools") is not body.get("tools"):
        new_body["tools"] = compressed_body["tools"]

    return new_body, stats

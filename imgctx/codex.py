"""Image a native Responses API request in place (the Codex CLI protocol).

The Codex CLI speaks the OpenAI Responses API natively: the request carries an
`input` array of typed items (message / function_call / function_call_output /
reasoning / ...) plus a top-level `instructions` slab, and expects a native
Responses SSE stream back. So this path is a pure transform+forward; unlike the
opencode relay, there is no Chat Completions translation in either direction.

Placement rules (Responses constraints, distinct from Chat and from Anthropic):
  * user messages hold `input_image` parts inline           -> replace text in place
  * function_call_output.output is a plain string (no image) -> stub it and emit the
    image(s) in a fresh user message right after, so the call_id pairing survives
  * instructions is a top-level string (no image)            -> stub it and prepend a
    leading image message

Every other item (function_call, reasoning, local_shell_call, ...) is preserved
byte-identical and in order, because Codex's agent loop and the ChatGPT backend's
strict call_id / reasoning pairing depend on it. This is why we transform the input
array in place instead of round-tripping through Chat Completions (which would drop
every non-message item).

Shared imaging primitives (budget, gating, accounting, factsheet, render) come from
transform.py so the instrument matches the Chat path; only the item placement differs.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from ._oauth import get_refresh_lock, post_refresh
from .factsheet import build_factsheet
from .models import model_supported
from .render import RenderedPage
from .transform import _BANNER, _Budget, _account, _has_image, TransformStats


def _responses_text_of(content) -> str:
    """Plain text of a Responses content value (str or part list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and p.get("type") in ("input_text", "output_text", "text"):
                out.append(p.get("text", ""))
        return "\n".join(out)
    return ""


def _fco_text(output) -> str:
    """Flatten a function_call_output `output` to text. Codex sends it as a plain
    string most of the time, but tolerate the structured list/dict shapes too."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return _responses_text_of(output)
    if isinstance(output, dict):
        if isinstance(output.get("content"), (str, list)):
            return _responses_text_of(output["content"])
        if isinstance(output.get("output"), str):
            return output["output"]
    return json.dumps(output) if output else ""


def _image_part(page: RenderedPage, detail: str) -> dict:
    return {"type": "input_image", "detail": detail,
            "image_url": f"data:image/png;base64,{page.b64}"}


def _image_message(pages: list[RenderedPage], text: str, settings: Settings) -> dict:
    parts: list[dict] = [{"type": "input_text", "text": _BANNER}]
    for pg in pages:
        parts.append(_image_part(pg, settings.image_detail))
    if settings.factsheet:
        sheet = build_factsheet(text)
        if sheet:
            parts.append({"type": "input_text", "text": sheet})
    return {"type": "message", "role": "user", "content": parts}


def transform_responses_native(body: dict, settings: Settings) -> tuple[dict, TransformStats]:
    """Image a native Responses API request in place, preserving every input item.

    Images (a) large function_call_output tool results, (b) older large user
    messages, and (c) the system `instructions` slab, while leaving function_call,
    reasoning, and all other items byte-identical and in order. Fail-open: any shape
    issue returns the original body untouched."""
    stats = TransformStats()
    try:
        model = body.get("model")
        stats.model = model
        if not settings.enabled:
            stats.reason = "disabled"
            return body, stats
        if not model_supported(model, settings):
            stats.reason = "unsupported_model"
            return body, stats
        input_data = body.get("input")
        if not isinstance(input_data, list) or not input_data:
            stats.reason = "no_input"
            return body, stats
        instructions = body.get("instructions") or ""

        # Keep the live/last user turn as text (high-fidelity actionable instruction);
        # older user turns are eligible for imaging. Tool results are imaged regardless
        # of recency; the freshest large tool output is exactly what we want imaged.
        last_user_idx = -1
        for i, it in enumerate(input_data):
            if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "user":
                last_user_idx = i

        # Cheap pre-filter on total compressible mass.
        total = len(instructions) if settings.compress_system else 0
        for i, it in enumerate(input_data):
            if not isinstance(it, dict):
                continue
            t = it.get("type")
            if t == "function_call_output" and settings.compress_tool_results:
                total += len(_fco_text(it.get("output")))
            elif (t == "message" and it.get("role") == "user"
                    and settings.compress_user_text and i != last_user_idx):
                total += len(_responses_text_of(it.get("content")))
        if total < settings.min_total_chars:
            stats.reason = "below_total_threshold"
            return body, stats

        budget = _Budget(settings)
        new_input: list = []
        new_instructions = instructions

        # --- system instructions: stub + leading image message ---
        if settings.compress_system and instructions:
            pages = budget.render_gate(instructions, settings.min_system_chars)
            if pages:
                new_input.append(_image_message(pages, instructions, settings))
                new_instructions = (
                    "The full system instructions are provided as rendered page "
                    "image(s) in the first message. Follow them as authoritative context."
                )
                _account(stats, "system", instructions, pages, settings)

        for i, it in enumerate(input_data):
            if not isinstance(it, dict):
                new_input.append(it)
                continue
            t = it.get("type")

            # --- tool results: stub the output + trailing image message ---
            if t == "function_call_output" and settings.compress_tool_results:
                text = _fco_text(it.get("output"))
                pages = budget.render_gate(text, settings.min_tool_result_chars)
                if pages:
                    stub = dict(it)
                    stub["output"] = "[Large tool output rendered as image(s) in the next message.]"
                    new_input.append(stub)
                    new_input.append(_image_message(pages, text, settings))
                    _account(stats, "tool_result", text, pages, settings)
                    continue

            # --- older user text: image in place (keep the live/last turn text) ---
            if (t == "message" and it.get("role") == "user" and settings.compress_user_text
                    and i != last_user_idx and not _has_image(it.get("content"))):
                text = _responses_text_of(it.get("content"))
                pages = budget.render_gate(text, settings.min_user_text_chars)
                if pages:
                    parts: list[dict] = [{"type": "input_text", "text": _BANNER}]
                    for pg in pages:
                        parts.append(_image_part(pg, settings.image_detail))
                    if settings.factsheet:
                        sheet = build_factsheet(text)
                        if sheet:
                            parts.append({"type": "input_text", "text": sheet})
                    nm = dict(it)
                    nm["content"] = parts
                    new_input.append(nm)
                    _account(stats, "user_text", text, pages, settings)
                    continue

            new_input.append(it)

        if stats.imaged_blocks == 0:
            stats.reason = "nothing_profitable"
            return body, stats

        new_body = dict(body)
        new_body["input"] = new_input
        if new_instructions != instructions:
            new_body["instructions"] = new_instructions
        stats.compressed = True
        stats.reason = "ok"
        return new_body, stats
    except Exception as e:  # fail-open: never break the request
        stats.compressed = False
        stats.reason = f"error:{type(e).__name__}"
        return body, stats


# --- OAuth: Codex's nested `tokens` credential shape ---

def read_oauth_token(settings: Settings) -> dict | None:
    """Read the Codex CLI's ChatGPT OAuth tokens at forward time (so Codex's own
    background refreshes are picked up). Codex's auth.json nests the tokens under a
    `tokens` object, a different shape from opencode's flat `openai` object.

    Returns {"access": str, "refresh": str, "account_id": str} or None.
    """
    try:
        path = Path(settings.codex_credentials_path).expanduser()
        data = json.loads(path.read_text())
        tok = data.get("tokens") or {}
        access = tok.get("access_token", "")
        refresh = tok.get("refresh_token", "")
        account_id = tok.get("account_id", "")
        if not access or not account_id:
            return None
        return {"access": access, "refresh": refresh, "account_id": account_id}
    except Exception:
        return None


async def refresh_token(settings: Settings) -> dict | None:
    """Refresh Codex's ChatGPT OAuth access token and write it back to Codex's
    auth.json (its own nested `tokens` shape). Serializes through the shared lock.
    Best-effort: returns None on any failure."""
    async with get_refresh_lock():
        tokens = read_oauth_token(settings)
        if not tokens or not tokens.get("refresh"):
            return None

        body = await post_refresh(tokens["refresh"])
        if not body:
            return None

        new_access = body.get("access_token", "")
        new_refresh = body.get("refresh_token", tokens["refresh"])
        if not new_access:
            return None

        try:
            path = Path(settings.codex_credentials_path).expanduser()
            current = json.loads(path.read_text())
            current.setdefault("tokens", {})
            current["tokens"]["access_token"] = new_access
            current["tokens"]["refresh_token"] = new_refresh
            if body.get("id_token"):
                current["tokens"]["id_token"] = body["id_token"]
            path.write_text(json.dumps(current, indent=2))
        except Exception:
            pass  # Non-fatal: Codex will refresh on its own next run

        return {"access": new_access, "refresh": new_refresh,
                "account_id": tokens.get("account_id", "")}

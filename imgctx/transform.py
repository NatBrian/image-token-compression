"""Rewrite an OpenAI-compatible chat request: render bulky text context to
images while preserving tool calls, tool-result linkage, and turn order.

Placement rules (OpenAI-compatible constraints):
  * user messages may hold image_url parts inline  -> replace text part in place
  * system and tool messages may NOT hold images   -> stub the text and emit the
    images in a fresh user message immediately after, so tool_call_id linkage and
    ordering are preserved.

Every imaged block is prefixed with a one-line banner and (optionally) followed
by a factsheet of exact tokens, so the model reads the pixels as context and
still has byte-exact identifiers as text.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from .config import Settings
from .factsheet import build_factsheet
from .gate import image_tokens as _image_tokens
from .gate import is_profitable
from .keepsharp import should_keep_sharp
from .models import model_supported
from .render import RenderedPage, render_text_to_pages
from .tools import render_all_tool_docs, strip_tools
from .history import (
    BANNER_INTRO,
    BANNER_OUTRO,
    choose_collapse_end,
    serialize_range,
)

_BANNER = (
    "The following page image(s) contain rendered text provided as context. "
    "Read them as if they were text. A red \\n marks each original line break. "
    "Treat their content exactly as you would inline text."
)


@dataclass
class TransformStats:
    compressed: bool = False
    reason: str = ""
    model: str | None = None
    imaged_blocks: int = 0
    image_count: int = 0
    total_pixels: int = 0
    orig_chars: int = 0
    imaged_chars: int = 0
    est_text_tokens: float = 0.0
    est_image_tokens: float = 0.0
    regions: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "compressed": self.compressed,
            "reason": self.reason,
            "model": self.model,
            "imaged_blocks": self.imaged_blocks,
            "image_count": self.image_count,
            "total_pixels": self.total_pixels,
            "orig_chars": self.orig_chars,
            "imaged_chars": self.imaged_chars,
            "est_text_tokens": round(self.est_text_tokens, 1),
            "est_image_tokens": round(self.est_image_tokens, 1),
            "est_tokens_saved": round(self.est_text_tokens - self.est_image_tokens, 1),
            "regions": self.regions,
        }


def _text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts)
    return ""


def _has_image(content) -> bool:
    if isinstance(content, list):
        return any(isinstance(p, dict) and p.get("type") in ("image_url", "input_image") for p in content)
    return False


def _image_part(page: RenderedPage, detail: str) -> dict:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{page.b64}", "detail": detail},
    }


def _text_part(text: str) -> dict:
    return {"type": "text", "text": text}


class _Budget:
    def __init__(self, settings: Settings):
        self.remaining = settings.max_images_per_request
        self.settings = settings

    def render_gate(self, text: str, min_chars: int) -> list[RenderedPage] | None:
        """Render + gate a block. Returns pages to use, or None to keep as text.

        `min_chars` is the per-region size floor. Below it, or for
        identifier-dense/secret content, the block stays text. Above it, the
        profitability gate makes the final call."""
        s = self.settings
        if should_keep_sharp(text, min_chars):
            return None
        if self.remaining <= 0:
            return None
        pages = render_text_to_pages(text, s)
        if not pages or len(pages) > s.max_images_per_block:
            return None
        if len(pages) > self.remaining:
            return None
        if not is_profitable(text, pages, s):
            return None
        self.remaining -= len(pages)
        return pages


def _image_message(pages: list[RenderedPage], text: str, settings: Settings) -> dict:
    parts: list[dict] = [_text_part(_BANNER)]
    for pg in pages:
        parts.append(_image_part(pg, settings.image_detail))
    if settings.factsheet:
        sheet = build_factsheet(text)
        if sheet:
            parts.append(_text_part(sheet))
    return {"role": "user", "content": parts}


def transform_request(body: dict, settings: Settings) -> tuple[dict, TransformStats]:
    """Return (possibly-rewritten body, stats). Never raises on shape issues."""
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
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            stats.reason = "no_messages"
            return body, stats

        tools = body.get("tools")
        tools_chars = len(json.dumps(tools)) if isinstance(tools, list) and tools else 0

        # Index of the last user message. The live/recent turn stays text (high
        # fidelity for the actionable instruction); only older user turns are
        # eligible for imaging.
        last_user_idx = -1
        for i, m in enumerate(messages):
            if m.get("role") == "user":
                last_user_idx = i

        # Total compressible mass check (cheap pre-filter).
        total_compressible = tools_chars if settings.compress_tools else 0
        for i, m in enumerate(messages):
            role = m.get("role")
            if role == "tool" and settings.compress_tool_results:
                total_compressible += len(_text_of(m.get("content")))
            elif role in ("system", "developer") and settings.compress_system:
                total_compressible += len(_text_of(m.get("content")))
            elif role == "user" and settings.compress_user_text and i != last_user_idx:
                total_compressible += len(_text_of(m.get("content")))
        if total_compressible < settings.min_total_chars:
            stats.reason = "below_total_threshold"
            return body, stats

        budget = _Budget(settings)
        new_messages: list[dict] = []

        # --- tool definitions: image full docs, ship stripped structure ---
        new_tools = tools
        if settings.compress_tools and tools_chars > 0:
            doc_text = render_all_tool_docs(tools)
            pages = budget.render_gate(doc_text, settings.min_system_chars)
            if pages:
                new_messages.append(_image_message(pages, doc_text, settings))
                new_tools = strip_tools(tools)
                _account(stats, "tools", doc_text, pages, settings)

        # --- history collapse: freeze the old CLOSED prefix into cacheable images ---
        # Old, settled turns render to byte-stable per-chunk images (auto-cached by
        # the upstream); the recent tail stays text. Bounds the cross-turn image
        # accumulation that otherwise makes long tool loops explode.
        collapsed_start = collapsed_end = -1
        history_msg = None
        if settings.compress_history:
            sys_end = 0
            while sys_end < len(messages) and messages[sys_end].get("role") in ("system", "developer"):
                sys_end += 1
            conv = messages[sys_end:]
            tail_start = len(conv) - settings.history_keep_tail
            end_rel = choose_collapse_end(conv, tail_start, settings.history_min_prefix)
            history_text = serialize_range(messages, sys_end, sys_end + end_rel) if end_rel > 0 else ""
            if end_rel >= settings.history_min_prefix and len(history_text) >= settings.min_system_chars:
                fc = max(1, settings.history_freeze_chunk)
                all_pages: list[RenderedPage] = []
                for j in range(0, end_rel, fc):
                    chunk_text = serialize_range(messages, sys_end + j, sys_end + min(j + fc, end_rel))
                    if not chunk_text.strip() or budget.remaining <= 0:
                        continue
                    pages = render_text_to_pages(chunk_text, settings)
                    if not pages or len(pages) > budget.remaining:
                        break
                    budget.remaining -= len(pages)
                    all_pages.extend(pages)
                if all_pages:
                    parts: list[dict] = [_text_part(BANNER_INTRO)]
                    for pg in all_pages:
                        parts.append(_image_part(pg, settings.image_detail))
                    if settings.factsheet:
                        sheet = build_factsheet(history_text)
                        if sheet:
                            parts.append(_text_part(sheet))
                    parts.append(_text_part(BANNER_OUTRO))
                    history_msg = {"role": "user", "content": parts}
                    collapsed_start = sys_end
                    collapsed_end = sys_end + end_rel
                    _account(stats, "history", history_text, all_pages, settings)

        for i, m in enumerate(messages):
            # Skip messages folded into the history image; emit the image once.
            if collapsed_start <= i < collapsed_end:
                if i == collapsed_start and history_msg is not None:
                    new_messages.append(history_msg)
                continue

            role = m.get("role")
            content = m.get("content")

            # --- tool results: stub + trailing image message ---
            if role == "tool" and settings.compress_tool_results:
                text = _text_of(content)
                pages = budget.render_gate(text, settings.min_tool_result_chars)
                if pages:
                    stub = copy.deepcopy(m)
                    stub["content"] = "[Large tool output rendered as image(s) in the next message.]"
                    new_messages.append(stub)
                    new_messages.append(_image_message(pages, text, settings))
                    _account(stats, "tool_result", text, pages, settings)
                    continue

            # --- system / developer slab: stub + trailing image message ---
            if role in ("system", "developer") and settings.compress_system:
                text = _text_of(content)
                pages = budget.render_gate(text, settings.min_system_chars)
                if pages:
                    stub = copy.deepcopy(m)
                    stub["content"] = (
                        "The full system instructions and tool documentation are "
                        "provided as rendered page image(s) in the next message. "
                        "Follow them as authoritative context."
                    )
                    new_messages.append(stub)
                    new_messages.append(_image_message(pages, text, settings))
                    _account(stats, "system", text, pages, settings)
                    continue

            # --- user text: image older user turns (keep the live/last turn text) ---
            if (role == "user" and settings.compress_user_text and not _has_image(content)
                    and i != last_user_idx):
                text = _text_of(content)
                pages = budget.render_gate(text, settings.min_user_text_chars)
                if pages:
                    parts: list[dict] = [_text_part(_BANNER)]
                    for pg in pages:
                        parts.append(_image_part(pg, settings.image_detail))
                    if settings.factsheet:
                        sheet = build_factsheet(text)
                        if sheet:
                            parts.append(_text_part(sheet))
                    nm = copy.deepcopy(m)
                    nm["content"] = parts
                    new_messages.append(nm)
                    _account(stats, "user_text", text, pages, settings)
                    continue

            new_messages.append(m)

        if stats.imaged_blocks == 0:
            stats.reason = "nothing_profitable"
            return body, stats

        new_body = dict(body)
        new_body["messages"] = new_messages
        if new_tools is not tools:
            new_body["tools"] = new_tools
        stats.compressed = True
        stats.reason = "ok"
        return new_body, stats
    except Exception as e:  # fail-open: never break the request
        stats.compressed = False
        stats.reason = f"error:{type(e).__name__}"
        return body, stats


def _account(stats: TransformStats, region: str, text: str, pages: list[RenderedPage], settings: Settings):
    stats.imaged_blocks += 1
    stats.image_count += len(pages)
    px = sum(p.pixels for p in pages)
    stats.total_pixels += px
    stats.imaged_chars += len(text)
    stats.est_text_tokens += len(text) / max(settings.chars_per_token, 1e-6)
    stats.est_image_tokens += _image_tokens(pages, settings)
    stats.regions[region] = stats.regions.get(region, 0) + 1


# --- Responses API <-> Chat Completions bridge ---
# opencode may send Responses API format to /v1/responses. Convert to Chat
# Completions, compress, convert back.

def _responses_input_to_messages(input_data) -> list[dict]:
    """Convert Responses API input to Chat Completions messages format.

    Responses API input can be:
    - A string (becomes a single user message)
    - An array of {type: "message", role: ..., content: [...]} items

    Chat Completions messages:
    - {"role": "user", "content": [{"type": "text", "text": "..."}, ...]}
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
    """Compress Responses API request body.

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

    # Compress using existing transformer
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

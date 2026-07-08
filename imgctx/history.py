"""History collapse for an OpenAI-compatible chat request.

Problem it solves: in a long tool loop, each new call re-sends the accumulating
imaged tool outputs, so cost compounds. Fix: collapse the OLD, settled part of
the conversation into a few images ONCE and keep the recent tail as text.

Two properties make it cheap:
  * Closed-prefix only, we never cut between a tool call and its result
    (`find_closed_prefix_boundary`), so the agent loop never breaks.
  * Grid-frozen, the collapse boundary snaps to an absolute grid of
    `freeze_chunk` messages, and each chunk is rendered from a FIXED message
    range. Its pixels therefore stay byte-identical as the conversation grows, so
    the provider's automatic prompt cache reads it back cheaply (mimo/zen report
    `cached_tokens`) instead of re-billing it every turn. A per-turn moving
    boundary would change the bytes every call and never cache, that is the
    make-or-break detail.

We target an auto-caching OpenAI-compatible upstream, so there is no manual
cache-marker machinery, byte-stability alone suffices.
"""
from __future__ import annotations

import json


def _text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                out.append(p.get("text", ""))
            elif isinstance(p, dict) and p.get("type") == "image_url":
                out.append("[image]")
            elif isinstance(p, str):
                out.append(p)
        return "\n".join(out)
    return ""


def has_image(content) -> bool:
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") in ("image_url", "input_image") for p in content
    )


def find_closed_prefix_boundary(messages: list[dict], cutoff_exclusive: int) -> int:
    """Last index < cutoff_exclusive where every tool call is matched by its
    result. Returns -1 if none. Robust to parallel/interleaved tool calls."""
    if cutoff_exclusive <= 0:
        return -1
    open_set: set[str] = set()
    last_closed = -1
    limit = min(cutoff_exclusive, len(messages))
    for i in range(limit):
        m = messages[i]
        role = m.get("role")
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                tid = tc.get("id")
                if isinstance(tid, str):
                    open_set.add(tid)
        elif role == "tool":
            tid = m.get("tool_call_id")
            if isinstance(tid, str):
                open_set.discard(tid)
        if not open_set:
            last_closed = i
    return last_closed


def _msg_to_history_text(m: dict, idx: int) -> str:
    role = m.get("role")
    body_parts: list[str] = []
    txt = _text_of(m.get("content"))
    if txt.strip():
        body_parts.append(txt)
    if role == "assistant":
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            name = fn.get("name", "?")
            args = fn.get("arguments", "")
            if not isinstance(args, str):
                try:
                    args = json.dumps(args)
                except Exception:
                    args = str(args)
            body_parts.append(f"[tool_use {name}]\n{args}")
        tag = "assistant"
    elif role == "tool":
        body_parts = [f"[tool_result]\n{txt}"] if txt.strip() else ["[tool_result]"]
        tag = "tool"
    else:
        tag = "user"
    body = "\n".join(body_parts)
    # Absolute turn index t="i", stable once the turn closes, so a frozen chunk
    # stays byte-identical (and cacheable) as the conversation grows.
    return f'<{tag} t="{idx}">\n{body}\n</{tag}>'


def serialize_range(messages: list[dict], start: int, end: int) -> str:
    parts = []
    for i in range(start, end):
        seg = _msg_to_history_text(messages[i], i)
        if seg.strip():
            parts.append(seg)
    return "\n\n".join(parts)


def choose_collapse_end(messages: list[dict], tail_start: int, min_prefix: int) -> int:
    """Number of leading messages to collapse: the largest CLOSED-prefix length
    <= tail_start (so the tail never contains an orphaned tool call). Returns 0 if
    the closed prefix is shorter than `min_prefix`.

    Note: the collapse boundary itself must be closed, but the freeze-chunk slices
    used at render time need NOT be, they are only byte-stability units. In a tool
    loop, closed boundaries fall on every other message, so snapping the boundary to
    a chunk grid would almost never align; chunking is applied to the render, not the
    boundary."""
    raw = find_closed_prefix_boundary(messages, tail_start)  # last closed index < tail_start
    if raw < 0:
        return 0
    closed_len = raw + 1
    return closed_len if closed_len >= min_prefix else 0


BANNER_INTRO = (
    "[Earlier turns of THIS conversation, rendered as the image(s) below. Each turn "
    'is wrapped in <user t="N">, <assistant t="N">, or <tool t="N"> tags where larger '
    "N = more recent. Treat this as prior context, not the current request. A red \\n "
    "marks each original line break.]"
)
BANNER_OUTRO = "[End of earlier conversation. The live request is the text that follows below.]"

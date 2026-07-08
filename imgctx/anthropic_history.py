"""History collapse for an Anthropic Messages request (adapted to the Anthropic
block shape).

Problem it solves: in a long agent loop, each new turn re-sends the accumulating
tool outputs. If those are imaged per-turn (as the base transform does), their
pixel bytes are fresh every turn -> Anthropic bills them at the cache-CREATE rate
(1.25x) instead of cache-READ (0.1x). This is the dominant residual cost of the
Anthropic path on a cache-cheap model.

Fix: collapse the OLD, settled part of the conversation
into image(s) ONCE and keep the recent tail as TEXT. Two properties make it pay:
  * Closed-prefix only: never cut between a tool_use and its tool_result
    (`find_closed_prefix_boundary`), so the agent loop never breaks.
  * Byte-frozen: the collapse cutoff snaps to an absolute `freeze_chunk` grid and
    each chunk renders from a FIXED message range, so a completed chunk's PNG bytes
    stay byte-identical as the conversation grows -> Anthropic's prompt cache reads
    it back at 0.1x instead of re-creating it. A per-turn moving boundary would
    change the bytes every call and never cache -- the make-or-break detail.

Anthropic specifics vs the OpenAI port: tool_use lives in assistant content blocks
and tool_result inside user content blocks (no `role:"tool"`); images are
`{type:"image", source:{base64}}`. The caller (Claude Code) also places cache_control
breakpoints, so we relocate (never add) the slab anchor onto the last byte-stable
history image so slab + history cache as one stable prefix.
"""
from __future__ import annotations

import re

from .config import Settings
from .factsheet import build_factsheet
from .gate import image_tokens as _image_tokens
from .gate import is_profitable
from .render import RenderedPage, render_text_to_pages

HISTORY_INTRO = (
    "[Earlier turns of THIS conversation, rendered as the image(s) below. Each turn "
    'is wrapped in <user t="N"> / <assistant t="N"> tags where larger N = more '
    "recent. Treat this as prior context, not the current request. A red \\n marks "
    "each original line break.]"
)
HISTORY_OUTRO = "[End of earlier conversation. The live request is the text that follows below.]"

# Claude Code appends this to Edit/Write tool_results; it is stale once the turn is
# frozen into history (the file may have changed since). Rewrite so a model reading
# old history does not skip a required Read. Rewrites stale freshness hints.
_FRESHNESS_HINT = re.compile(
    r"\(file state is current in your\s+context, no need to Read it back\)")
_STALE_NOTE = ("(state as of this PRIOR turn, the file may have changed since; "
               "Read it again before editing)")


def _stale_hints(text: str) -> str:
    return _FRESHNESS_HINT.sub(_STALE_NOTE, text)


def find_closed_prefix_boundary(messages: list[dict], cutoff_exclusive: int) -> int:
    """Last index < cutoff_exclusive where every tool_use id is matched by its
    tool_result in [0..i]. Returns -1 if none. Robust to parallel/interleaved calls.
    Anthropic shape: tool_use in assistant blocks, tool_result in user blocks."""
    if cutoff_exclusive <= 0:
        return -1
    open_set: set[str] = set()
    last_closed = -1
    limit = min(cutoff_exclusive, len(messages))
    for i in range(limit):
        m = messages[i]
        content = m.get("content")
        role = m.get("role")
        if not isinstance(content, list):
            if not open_set:
                last_closed = i  # plain string turn, no tool blocks
            continue
        if role == "assistant":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tid = b.get("id")
                    if isinstance(tid, str):
                        open_set.add(tid)
        elif role == "user":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tid = b.get("tool_use_id")
                    if isinstance(tid, str):
                        open_set.discard(tid)
        if not open_set:
            last_closed = i
    return last_closed


def _blocks_to_text(content) -> str:
    """Linearise Anthropic content blocks to text. tool_use -> `[tool_use name]\\nargs`,
    tool_result -> `[tool_result]\\ninner`, images -> `[image]` placeholder."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    import json as _json
    parts: list[str] = []
    for b in content:
        if not isinstance(b, dict):
            if isinstance(b, str):
                parts.append(b)
            continue
        t = b.get("type")
        if t == "text":
            parts.append(b.get("text", ""))
        elif t == "tool_use":
            try:
                args = _json.dumps(b.get("input"), ensure_ascii=False)
            except Exception:
                args = str(b.get("input"))
            parts.append(f"[tool_use {b.get('name', '?')}]\n{args}")
        elif t == "tool_result":
            inner = b.get("content")
            if isinstance(inner, str):
                itext = inner
            elif isinstance(inner, list):
                sub: list[str] = []
                for s in inner:
                    if isinstance(s, dict) and s.get("type") == "text":
                        sub.append(s.get("text", ""))
                    elif isinstance(s, dict) and s.get("type") == "image":
                        sub.append("[image]")
                itext = "\n".join(sub)
            else:
                itext = ""
            err = " (error)" if b.get("is_error") else ""
            parts.append(f"[tool_result{err}]\n{_stale_hints(itext)}")
        elif t == "image":
            parts.append("[image]")
        # thinking/other -> drop
    return "\n\n".join(p for p in parts if p)


def messages_to_history_text(messages: list[dict], up_to_exclusive: int,
                             from_inclusive: int = 0) -> str:
    """Wrap each turn in <user t="i"> / <assistant t="i"> with ABSOLUTE index i so a
    frozen chunk stays byte-identical as the conversation grows (cache_read survives)."""
    out: list[str] = []
    for i in range(from_inclusive, min(up_to_exclusive, len(messages))):
        m = messages[i]
        body = _blocks_to_text(m.get("content"))
        if not body.strip():
            continue
        tag = "assistant" if m.get("role") == "assistant" else "user"
        out.append(f'<{tag} t="{i}">\n{body}\n</{tag}>')
    return "\n\n".join(out)


def _img_block(page: RenderedPage) -> dict:
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": page.b64}}


class HistoryInfo:
    __slots__ = ("reason", "collapsed_turns", "collapsed_chars", "collapsed_images",
                 "carry_over_ordinal", "collapsed_text", "est_image_tokens", "total_pixels")

    def __init__(self):
        self.reason = None
        self.collapsed_turns = 0
        self.collapsed_chars = 0
        self.collapsed_images = 0
        self.carry_over_ordinal = -1
        self.collapsed_text = ""
        self.est_image_tokens = 0.0
        self.total_pixels = 0


def collapse_history(messages: list[dict], settings: Settings, protected_prefix: int,
                     images_remaining: int) -> tuple[list[dict], HistoryInfo]:
    """Freeze the old closed prefix [protected_prefix..boundary] into byte-stable
    image(s); keep the last `history_keep_tail` turns as text. Returns (new_messages,
    info). new_messages == messages (unchanged) when collapse does not fire."""
    info = HistoryInfo()
    if not messages:
        info.reason = "no_history"
        return messages, info
    keep_tail = settings.history_keep_tail
    min_prefix = settings.history_min_prefix
    chunk = settings.history_freeze_chunk

    raw_cutoff = len(messages) - keep_tail
    if chunk > 0:
        cutoff = min(raw_cutoff,
                     max(min_prefix + protected_prefix,
                         (raw_cutoff // chunk) * chunk))
    else:
        cutoff = raw_cutoff

    boundary = find_closed_prefix_boundary(messages, cutoff)
    if boundary < 0:
        info.reason = "no_closed_prefix"
        return messages, info
    collapse_len = boundary + 1
    if collapse_len - protected_prefix < min_prefix:
        info.reason = "prefix_too_short"
        return messages, info

    full_text = messages_to_history_text(messages, collapse_len, protected_prefix)
    if not full_text:
        info.reason = "render_empty"
        return messages, info

    # Chunk-end grid (absolute, anchored at protected_prefix) so each completed chunk
    # is a pure function of its message range -> byte-identical across turns.
    step = chunk if chunk > 0 else (collapse_len - protected_prefix)
    ends: set[int] = set()
    e = protected_prefix + step
    while e < collapse_len:
        ends.add(e)
        e += step
    ends.add(collapse_len)
    sorted_ends = sorted(x for x in ends if protected_prefix < x <= collapse_len)

    # Carry-over anchor = largest FULLY grid-aligned chunk end strictly before
    # collapse_len (byte-frozen, unlike the newest partial chunk).
    carry_over_end = -1
    e = protected_prefix + step
    while e < collapse_len:
        carry_over_end = e
        e += step

    images: list[dict] = []
    carry_ordinal = -1
    chunk_start = protected_prefix
    for chunk_end in sorted_ends:
        seg = messages_to_history_text(messages, chunk_end, chunk_start)
        chunk_start = chunk_end
        if not seg:
            continue
        if images_remaining - len(images) <= 0:
            break
        pages = render_text_to_pages(seg, settings)
        if not pages:
            continue
        # Per-chunk profitability: only image a chunk that actually saves tokens.
        if not is_profitable(seg, pages, settings):
            continue
        take = min(len(pages), settings.max_images_per_block,
                   images_remaining - len(images))
        taken = pages[:take]
        for pg in taken:
            images.append(_img_block(pg))
            info.total_pixels += pg.pixels
        info.est_image_tokens += _image_tokens(taken, settings)
        if chunk_end == carry_over_end:
            carry_ordinal = len(images) - 1

    if not images:
        info.reason = "not_profitable"
        return messages, info

    synthetic_content: list[dict] = [{"type": "text", "text": HISTORY_INTRO}]
    synthetic_content.extend(images)
    if settings.factsheet:
        sheet = build_factsheet(full_text)
        if sheet:
            synthetic_content.append({"type": "text", "text": sheet})
    synthetic_content.append({"type": "text", "text": HISTORY_OUTRO})
    synthetic = {"role": "user", "content": synthetic_content}

    new_messages = messages[:protected_prefix] + [synthetic] + messages[collapse_len:]
    info.reason = "collapsed"
    info.collapsed_turns = collapse_len - protected_prefix
    info.collapsed_chars = len(full_text)
    info.collapsed_images = len(images)
    info.carry_over_ordinal = carry_ordinal
    info.collapsed_text = full_text
    return new_messages, info


def relocate_anchor_to_history_image(messages: list[dict], carry_over_ordinal: int) -> None:
    """Move the slab's single cache_control marker off the slab image and onto the
    carry-over (byte-stable) history image, so slab + history cache as one stable
    prefix. Pure relocation: acts only when a slab image already carries the anchor,
    so the total marker count never increases. No-op unless a byte-frozen carry-over
    chunk exists (carry_over_ordinal >= 0)."""
    if carry_over_ordinal < 0:
        return
    # Find the synthetic history message (its first block is HISTORY_INTRO) and its
    # image blocks in order.
    hist_imgs: list[dict] = []
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list) or not content:
            continue
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text" and first.get("text") == HISTORY_INTRO:
            hist_imgs = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
            break
    if not hist_imgs or carry_over_ordinal >= len(hist_imgs):
        return
    target = hist_imgs[carry_over_ordinal]

    # The slab anchor is the marked image BEFORE the '[End of rendered context...]'
    # sentinel in the slab-bearing message.
    from .anthropic import _SLAB_SENTINEL
    slab_anchor = None
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        if not any(isinstance(b, dict) and b.get("type") == "text"
                   and b.get("text") == _SLAB_SENTINEL for b in content):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text") == _SLAB_SENTINEL:
                break
            if isinstance(b, dict) and b.get("type") == "image" and b.get("cache_control") is not None:
                slab_anchor = b
        break
    if slab_anchor is None:
        return  # nothing to relocate -> never add a marker
    target["cache_control"] = slab_anchor["cache_control"]
    del slab_anchor["cache_control"]

"""Rewrite an Anthropic Messages API request: render bulky text context to
images while preserving tool-call linkage and turn structure.

Anthropic differs from the OpenAI chat shape in ways that matter here:
  * `system` is a TOP-LEVEL field (string or list of text blocks) and cannot hold
    images, so an imaged system prompt is injected as image blocks prepended to the
    first user message, and `system` is replaced with a short stub.
  * tool outputs are `tool_result` blocks INSIDE user messages (keyed by
    `tool_use_id`), and a tool_result's `content` may itself be a list of blocks,
    including images, so a large tool output is compressed in place by swapping its
    content for `[stub, image(s), factsheet]`, keeping the id linkage intact.
  * tools carry `input_schema` (not `function.parameters`); the annotation-stripped
    structure stays for the validator while the full docs move into the image.
  * images are `{type:"image", source:{type:"base64", media_type, data}}`.

The big static context (system + tool docs) is imaged once into the first user
message and marked with a single `cache_control: ephemeral` breakpoint so it is
cache-read on later turns instead of re-billed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .config import Settings
from .factsheet import build_factsheet
from .gate import image_tokens as _image_tokens
from .gate import is_profitable
from .keepsharp import should_keep_sharp
from .render import RenderedPage, render_text_to_pages
from .schema_strip import schema_has_structure, strip_schema_descriptions
from .transform import TransformStats, _account
from .anthropic_history import collapse_history, relocate_anchor_to_history_image

# Tools whose stub keeps a read-before-edit precondition after docs move to image.
_READ_FIRST = {"edit", "write", "notebookedit", "str_replace_editor", "apply_patch", "multiedit"}

_BANNER = (
    "The following page image(s) contain rendered text provided as context. "
    "Read them as if they were text. A red \\n marks each original line break. "
    "Treat their content exactly as you would inline text."
)
_SYSTEM_STUB = (
    "The full system instructions and tool documentation are provided as rendered "
    "page image(s) at the start of the first user message. Follow them as "
    "authoritative context."
)
_SLAB_SENTINEL = "[End of rendered context. The conversation continues below.]"


def _safe_insert_index(content: list) -> int:
    """Return the index at which the slab may be inserted without splitting a
    leading tool_result run (Anthropic wants tool_result blocks first)."""
    i = 0
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            i += 1
        else:
            break
    return i


def _append_tail_text(messages: list, last_user_idx: int, text: str) -> None:
    """Append a text block to the END of the last user message (the volatile tail)."""
    if last_user_idx < 0 or last_user_idx >= len(messages):
        return
    m = messages[last_user_idx]
    content = m.get("content")
    if isinstance(content, str):
        content = [_txt_block(content)] if content else []
    elif not isinstance(content, list):
        content = []
    content = list(content) + [_txt_block(text)]
    m["content"] = content


# --------------------------------------------------------------------------- #
# content helpers
# --------------------------------------------------------------------------- #
def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _blocks_text(content) -> str:
    """Concatenated text of a message/tool_result content (string or block list)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text", ""))
            elif isinstance(b, str):
                out.append(b)
        return "\n".join(out)
    return ""


def _content_has_image(content) -> bool:
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "image" for b in content
    )


def _img_block(page: RenderedPage, cache: bool = False) -> dict:
    b = {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": page.b64},
    }
    if cache:
        b["cache_control"] = {"type": "ephemeral"}
    return b


def _txt_block(text: str) -> dict:
    return {"type": "text", "text": text}


import re as _re

# Per-turn dynamic system sections that must be kept OUT of the imaged slab, else
# their turn-to-turn drift busts the slab cache (fresh cache_create at 1.25x instead
# of cache_read at 0.1x) AND imaging the cwd/git state mis-orients the agent. They are
# relocated to the live tail as TEXT via the system-partition helpers below
# (billing-line strip / markdown-env strip / static-dynamic split).

# XML-tagged volatile blocks Claude Code (and sibling agents) inject into the system
# prompt: env, cwd, git status, directory tree, per-turn reminders.
_DYNAMIC_BLOCK_TAGS = ("env", "context", "git_status", "directoryStructure", "system-reminder")
_DYNAMIC_BLOCK_RE = _re.compile(
    r"<(" + "|".join(_DYNAMIC_BLOCK_TAGS) + r")(\s[^>]*)?>[\s\S]*?</\1>")
# `# Environment` markdown section (no XML wrapper) -> stop at the NEXT markdown
# heading of ANY level (#{1,6}) or end of text.
_ENV_MD_RE = _re.compile(r"(?:^|\n)(# Environment\b[\s\S]*?)(?=\n#{1,6}\s|$)")
_BILLING_PREFIX = "x-anthropic-billing-header:"


def _strip_billing_line(text: str) -> tuple[str | None, str]:
    """Return (billing_line|None, body). Claude Code prepends a per-turn
    `x-anthropic-billing-header:` line; strip it off the FIRST line so it never
    reaches the slab image, and re-insert it as plain system text."""
    nl = text.find("\n")
    first = text if nl == -1 else text[:nl]
    if first.startswith(_BILLING_PREFIX):
        return first, ("" if nl == -1 else text[nl + 1:])
    return None, text


def _strip_markdown_env_section(text: str) -> tuple[str, str]:
    """Return (env_md, body): pull the `# Environment` markdown section out so it can
    stay text in the live tail while the rest is imaged."""
    m = _ENV_MD_RE.search(text)
    if not m:
        return "", text
    return m.group(1).rstrip(), text[:m.start()] + text[m.end():]


def _split_static_dynamic(text: str) -> tuple[str, str]:
    """Return (static_text, dynamic_text): remove the volatile XML-tagged blocks from
    the cacheable slab and collect them for the live tail. Collapse the blank-line runs
    left behind so the static bytes stay stable."""
    if not text:
        return "", ""
    dynamic_parts: list[str] = []
    static_buf: list[str] = []
    cursor = 0
    for m in _DYNAMIC_BLOCK_RE.finditer(text):
        static_buf.append(text[cursor:m.start()])
        dynamic_parts.append(m.group(0))
        cursor = m.end()
    static_buf.append(text[cursor:])
    static = _re.sub(r"\n{3,}", "\n\n", "".join(static_buf)).strip()
    return static, "\n\n".join(dynamic_parts)


def _static_len(text: str) -> int:
    """Chars that would land in the slab image after billing/env/tag removal."""
    _, body = _strip_billing_line(text)
    _, body = _strip_markdown_env_section(body)
    static, _ = _split_static_dynamic(body)
    return len(static)


def _partition_system(system):
    """Split the Anthropic system field into (keep_text_blocks, static_slab_text,
    tail_text, slab_cache_control). The system-partition stage:
      * billing header line -> kept as plain system text (never imaged),
      * `# Environment` markdown + <env>/<context>/<git_status>/... tag blocks ->
        tail_text (relocated to the live tail as text; keeps cache stable + agent
        oriented),
      * everything else -> the static slab image,
      * the cache_control marker of the LAST text block that actually contributes
        static (imaged) content is carried onto the slab image (relocation, never
        added). Non-text blocks pass through untouched as keep blocks."""
    blocks = system if isinstance(system, list) else (
        [{"type": "text", "text": system}] if isinstance(system, str) and system else [])
    text_parts: list[str] = []
    keep_nontext: list[dict] = []
    slab_cc = None
    for b in blocks:
        if not isinstance(b, dict) or b.get("type") != "text":
            keep_nontext.append(b)
            continue
        t = b.get("text", "") or ""
        text_parts.append(t)
        # last text block whose own static contribution is non-empty wins the marker
        if b.get("cache_control") is not None and _static_len(t) > 0:
            slab_cc = b["cache_control"]
    raw = "\n\n".join(text_parts)
    billing, body = _strip_billing_line(raw)
    env_md, body = _strip_markdown_env_section(body)
    static, dynamic = _split_static_dynamic(body)
    tail_text = "\n\n".join(p for p in (dynamic, env_md) if p)
    keep: list[dict] = []
    if billing:  # session/turn-volatile header stays TEXT, out of the slab image
        keep.append(_txt_block(billing))
    keep.extend(keep_nontext)
    return keep, static, tail_text, slab_cc


def _imaged_blocks(pages: list[RenderedPage], text: str, settings: Settings,
                   banner: str = _BANNER) -> list[dict]:
    """A banner + image page(s) + optional factsheet, as a list of content blocks."""
    parts: list[dict] = [_txt_block(banner)]
    for pg in pages:
        parts.append(_img_block(pg))
    if settings.factsheet:
        sheet = build_factsheet(text)
        if sheet:
            parts.append(_txt_block(sheet))
    return parts


# --------------------------------------------------------------------------- #
# gating
# --------------------------------------------------------------------------- #
class _Budget:
    def __init__(self, settings: Settings):
        self.remaining = settings.max_images_per_request
        self.settings = settings

    def gate(self, text: str, min_chars: int, ignore_sharp: bool = False) -> list[RenderedPage] | None:
        s = self.settings
        # Tool docs are JSON-dense so keep_sharp would veto them, but their
        # machine-readable schema stays as text (tool calls stay byte-exact), so
        # only the prose semantics move to pixels: safe to image regardless.
        if not ignore_sharp and should_keep_sharp(text, min_chars):
            return None
        if self.remaining <= 0:
            return None
        pages = render_text_to_pages(text, s)
        if not pages or len(pages) > s.max_images_per_block or len(pages) > self.remaining:
            return None
        if not is_profitable(text, pages, s):
            return None
        self.remaining -= len(pages)
        return pages


# --------------------------------------------------------------------------- #
# tools
# --------------------------------------------------------------------------- #
def _render_tool_docs(tools: list) -> str:
    docs = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if not name:
            continue
        parts = [f"## Tool: {name}"]
        desc = t.get("description")
        if desc:
            parts.append(str(desc))
        schema = t.get("input_schema")
        if isinstance(schema, dict):
            parts.append("```json\n" + json.dumps(schema, ensure_ascii=False) + "\n```")
        docs.append("\n".join(parts))
    if not docs:
        return ""
    header = (
        "# Tool Reference\n"
        "Full documentation for the tools available this turn. The tools[] field "
        "carries the machine-readable schema; use these docs for names, semantics, "
        "and parameters.\n"
    )
    return header + "\n\n".join(docs)


def _strip_tools(tools: list) -> list:
    """Strip descriptions/annotations from each tool's input_schema, keep structure.
    Built-in/typed tools (no input_schema) pass through untouched. cache_control is
    dropped, the static-image breakpoint replaces it."""
    out = []
    for t in tools:
        if not isinstance(t, dict) or "input_schema" not in t:
            out.append(t)
            continue
        nt = copy.deepcopy(t)
        nt.pop("cache_control", None)
        name = (nt.get("name") or "").lower()
        nt["description"] = "See Tool Reference image." + (
            " Read the target before editing." if name in _READ_FIRST else ""
        )
        schema = nt.get("input_schema")
        if isinstance(schema, dict):
            stripped = strip_schema_descriptions(schema)
            nt["input_schema"] = stripped if schema_has_structure(stripped) else schema
        out.append(nt)
    return out


# --------------------------------------------------------------------------- #
# main transform
# --------------------------------------------------------------------------- #
def transform_anthropic_request(body: dict, settings: Settings) -> tuple[dict, TransformStats]:
    """Return (possibly-rewritten body, stats). Never raises on shape issues."""
    stats = TransformStats()
    try:
        model = body.get("model")
        stats.model = model
        if not settings.enabled:
            stats.reason = "disabled"
            return body, stats
        if not settings.model_supported(model):
            stats.reason = "unsupported_model"
            return body, stats
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            stats.reason = "no_messages"
            return body, stats

        system = body.get("system")
        tools = body.get("tools")
        sys_text = _system_text(system)
        tools_chars = len(json.dumps(tools)) if isinstance(tools, list) and tools else 0

        # Cheap pre-filter on total compressible mass.
        last_user_idx = -1
        first_user_idx = -1
        for i, m in enumerate(messages):
            if m.get("role") == "user":
                if first_user_idx < 0:
                    first_user_idx = i
                last_user_idx = i
        total_compressible = 0
        if settings.compress_system:
            total_compressible += len(sys_text)
        if settings.compress_tools:
            total_compressible += tools_chars
        for i, m in enumerate(messages):
            if m.get("role") != "user":
                continue
            content = m.get("content")
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result" and settings.compress_tool_results:
                        total_compressible += len(_blocks_text(b.get("content")))
                    elif (b.get("type") == "text" and settings.compress_user_text
                          and i != last_user_idx):
                        total_compressible += len(b.get("text", "") or "")
            elif i != last_user_idx and settings.compress_user_text:
                total_compressible += len(_blocks_text(content))
        if total_compressible < settings.min_total_chars:
            stats.reason = "below_total_threshold"
            return body, stats

        budget = _Budget(settings)
        new_body = copy.deepcopy(body)
        messages = new_body.get("messages")
        # NOTE: we do NOT strip inherited cache_control. Claude Code places moving
        # breakpoints on the recent message tail that cache the growing conversation;
        # stripping them re-bills all of history as fresh input. We only RELOCATE the
        # marker of a region we actually image, so the total marker count is conserved
        # (never exceeds Anthropic's 4 cap, never loses the tail cache). Cache-aligned.

        # --- static slab: (static system) + (tool docs) -> image(s), one marker ---
        if settings.compress_system:
            keep_sys, static_sys, env_text, slab_cc = _partition_system(new_body.get("system"))
        else:
            keep_sys, static_sys, env_text, slab_cc = None, "", "", None

        slab_text_parts: list[str] = []
        if settings.compress_system and static_sys:
            slab_text_parts.append(static_sys)
        tool_docs = ""
        if settings.compress_tools and tools_chars > 0:
            tool_docs = _render_tool_docs(tools)
            if tool_docs:
                slab_text_parts.append(tool_docs)
        slab_text = "\n\n".join(slab_text_parts)

        slab_pages = budget.gate(slab_text, settings.min_system_chars, ignore_sharp=True) if slab_text else None
        if slab_pages and first_user_idx >= 0:
            slab_blocks: list[dict] = [_txt_block(_BANNER)]
            for k, pg in enumerate(slab_pages):
                img = _img_block(pg)
                if k == len(slab_pages) - 1 and slab_cc is not None:
                    img["cache_control"] = slab_cc  # relocate CC's marker (keeps TTL)
                slab_blocks.append(img)
            if settings.factsheet:
                sheet = build_factsheet(slab_text)
                if sheet:
                    slab_blocks.append(_txt_block(sheet))
            slab_blocks.append(_txt_block(_SLAB_SENTINEL))

            fu = messages[first_user_idx]
            orig = fu.get("content")
            orig_list = orig if isinstance(orig, list) else ([_txt_block(orig)] if orig else [])
            insert_at = _safe_insert_index(orig_list)  # after any leading tool_result run
            fu["content"] = orig_list[:insert_at] + slab_blocks + orig_list[insert_at:]

            # System field: keep only billing header + non-text remainder (markers
            # preserved); the static rules moved into the slab image and the volatile
            # env/tag text moved to the live tail. Rebuilt whenever we relocated (even
            # if static_sys is empty but tools imaged) so env is never duplicated in
            # both the system field and the tail.
            if settings.compress_system and keep_sys is not None:
                new_body["system"] = keep_sys if keep_sys else []
            if tool_docs:
                new_body["tools"] = _strip_tools(tools)
            _account(stats, "slab", slab_text, slab_pages, settings)
            if static_sys:
                stats.regions["system"] = stats.regions.get("system", 0) + 1
            if tool_docs:
                stats.regions["tools"] = stats.regions.get("tools", 0) + 1

            # Volatile env/cwd/git text -> END of the last user message (live tail,
            # stays text). Wrapped as a system-reminder so the agent attributes it as
            # injected context, not user prose. Cache-aligned.
            if env_text:
                _append_tail_text(
                    messages, last_user_idx,
                    "<system-reminder>\nContext relocated from the system prompt "
                    "(volatile per-turn environment state, not written by the user):"
                    f"\n\n{env_text}\n</system-reminder>")

        # --- history collapse: freeze the OLD closed prefix into byte-stable image(s)
        #     and keep the recent tail as TEXT. This is the fix for the per-turn
        #     cache-CREATE leak: re-imaging tool_results every turn bills fresh pixels
        #     at 1.25x, whereas a byte-frozen history chunk cache-READs at 0.1x. When
        #     it fires the tail stays text (recent turns stay text), so the
        #     per-message imaging below is skipped. ---
        collapsed = False
        if settings.compress_history and first_user_idx >= 0 and len(messages) > 1:
            protected = first_user_idx + 1
            new_msgs, hinfo = collapse_history(messages, settings, protected, budget.remaining)
            if hinfo.reason == "collapsed":
                new_body["messages"] = new_msgs
                messages = new_msgs
                budget.remaining -= hinfo.collapsed_images
                # account the history region for stats/est_tokens_saved
                stats.imaged_blocks += hinfo.collapsed_images
                stats.image_count += hinfo.collapsed_images
                stats.total_pixels += hinfo.total_pixels
                stats.imaged_chars += hinfo.collapsed_chars
                stats.est_text_tokens += hinfo.collapsed_chars / max(settings.chars_per_token, 1e-6)
                stats.est_image_tokens += hinfo.est_image_tokens
                stats.regions["history"] = stats.regions.get("history", 0) + 1
                # relocate the slab anchor onto the byte-stable carry-over history image
                # so slab + history cache as one stable prefix (only if a frozen chunk
                # exists; never adds a marker).
                relocate_anchor_to_history_image(messages, hinfo.carry_over_ordinal)
                collapsed = True

        # --- per-message: tool_result blocks + older user text (list or plain) ---
        # Skipped when history collapsed: the frozen prefix already holds the old
        # tool_results as byte-stable images, and the live tail stays text.
        for i, m in enumerate(messages):
            if collapsed:
                break
            if m.get("role") != "user":
                continue
            content = m.get("content")

            if isinstance(content, list):
                new_content: list = []
                for b in content:
                    if not isinstance(b, dict):
                        new_content.append(b)
                        continue
                    btype = b.get("type")
                    if btype == "tool_result" and settings.compress_tool_results:
                        inner = b.get("content")
                        if not _content_has_image(inner) and not b.get("is_error"):
                            txt = _blocks_text(inner)
                            pages = budget.gate(txt, settings.min_tool_result_chars)
                            if pages:
                                # Marker (if any) stays on the tool_result BLOCK.
                                b["content"] = _imaged_blocks(pages, txt, settings)
                                _account(stats, "tool_result", txt, pages, settings)
                        new_content.append(b)
                    elif (btype == "text" and settings.compress_user_text
                          and i != last_user_idx):
                        txt = b.get("text", "") or ""
                        pages = budget.gate(txt, settings.min_user_text_chars)
                        if pages:
                            new_content.extend(_imaged_blocks(pages, txt, settings))
                            _account(stats, "user_text", txt, pages, settings)
                        else:
                            new_content.append(b)
                    else:
                        new_content.append(b)
                m["content"] = new_content
                continue

            # Plain-string older user turn (not the live turn): image it.
            if settings.compress_user_text and i != last_user_idx and content:
                txt = _blocks_text(content)
                pages = budget.gate(txt, settings.min_user_text_chars)
                if pages:
                    m["content"] = _imaged_blocks(pages, txt, settings)
                    _account(stats, "user_text", txt, pages, settings)

        if stats.imaged_blocks == 0:
            stats.reason = "nothing_profitable"
            return body, stats

        stats.compressed = True
        stats.reason = "ok"
        return new_body, stats
    except Exception as e:  # fail-open: never break the request
        stats.compressed = False
        stats.reason = f"error:{type(e).__name__}"
        return body, stats


# --- OAuth + usage parsing for the Claude Code (Anthropic Messages) relay ---

def read_oauth_token(settings: Settings) -> str | None:
    """Read Claude Code's subscription OAuth access token at forward time so token
    refreshes are picked up. Returns None if unavailable."""
    try:
        d = json.loads(Path(settings.anthropic_credentials_path).expanduser().read_text())
        tok = d.get("claudeAiOauth", {}).get("accessToken")
        return tok if isinstance(tok, str) and tok else None
    except Exception:
        return None


def parse_usage(data: bytes) -> dict | None:
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

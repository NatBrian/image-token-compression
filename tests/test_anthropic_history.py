"""Tests for the Anthropic history-collapse path (imgctx/anthropic_history.py)."""
from __future__ import annotations

import json

from imgctx.config import Settings
from imgctx.anthropic import transform_anthropic_request
from imgctx.anthropic_history import (
    HISTORY_INTRO, collapse_history, find_closed_prefix_boundary,
    messages_to_history_text,
)


def _count_cc(o) -> int:
    n = 0
    if isinstance(o, dict):
        if "cache_control" in o:
            n += 1
        for v in o.values():
            n += _count_cc(v)
    elif isinstance(o, list):
        for v in o:
            n += _count_cc(v)
    return n


def _big(n: int) -> str:
    return "line of prior conversation content " * n


def _convo(n: int, chars: int = 40) -> list[dict]:
    """n closed plain turns, alternating user/assistant, each large."""
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": [{"type": "text", "text": f"turn {i}: " + _big(chars)}]})
    return msgs


def _body(messages: list[dict]) -> dict:
    big_sys = "You are Claude Code. " + ("Follow these operational rules carefully. " * 400)
    return {
        "model": "claude-haiku-4-5-20251001",
        "system": [{"type": "text", "text": big_sys, "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "Bash", "description": "Run a shell command. " * 300,
                   "input_schema": {"type": "object",
                                    "properties": {"command": {"type": "string"}},
                                    "required": ["command"]}}],
        "messages": messages,
    }


# --------------------------------------------------------------------------- #
# closed-prefix boundary
# --------------------------------------------------------------------------- #
def test_closed_prefix_never_splits_tool_pair():
    msgs = _convo(8)
    # append an OPEN tool_use with no matching result at the end of the window
    msgs.append({"role": "assistant", "content": [
        {"type": "tool_use", "id": "OPEN", "name": "Bash", "input": {"command": "ls"}}]})
    msgs.append({"role": "user", "content": [{"type": "text", "text": "still going"}]})
    # boundary must stop before the open tool_use (index 8)
    b = find_closed_prefix_boundary(msgs, len(msgs))
    assert b <= 7


def test_closed_prefix_matches_tool_result():
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "done"}]},
    ]
    # after the tool_result the prefix is closed at index 2
    assert find_closed_prefix_boundary(msgs, 3) == 2
    # before the result (cutoff 2) the last closed index is 0 (the plain user turn)
    assert find_closed_prefix_boundary(msgs, 2) == 0


# --------------------------------------------------------------------------- #
# collapse folds old turns, keeps tail as text
# --------------------------------------------------------------------------- #
def test_collapse_folds_old_turns_into_one_history_message():
    new, stats = transform_anthropic_request(_body(_convo(24)), Settings())
    assert stats.compressed
    assert "history" in stats.regions
    msgs = new["messages"]
    # exactly one synthetic history message, carrying image blocks
    hist = [m for m in msgs if isinstance(m.get("content"), list)
            and m["content"] and isinstance(m["content"][0], dict)
            and m["content"][0].get("text") == HISTORY_INTRO]
    assert len(hist) == 1
    assert any(b.get("type") == "image" for b in hist[0]["content"])


def test_collapse_keeps_tail_as_text():
    s = Settings()
    src = _convo(24)
    new, _ = transform_anthropic_request(_body(src), s)
    msgs = new["messages"]
    # the last keep_tail turns survive verbatim as text at the end (not imaged)
    tail = msgs[-s.history_keep_tail:]
    for m in tail:
        assert isinstance(m.get("content"), list)
        assert not any(b.get("type") == "image" for b in m["content"] if isinstance(b, dict))
    # last turn text is preserved
    assert "turn 23" in json.dumps(msgs[-1])


def test_collapse_shrinks_message_count():
    src = _convo(24)
    new, _ = transform_anthropic_request(_body(src), Settings())
    # 24 old turns fold into 1 synthetic message + protected head + tail
    assert len(new["messages"]) < len(src)


# --------------------------------------------------------------------------- #
# byte-stability (the make-or-break cache property)
# --------------------------------------------------------------------------- #
def _history_image_data(new: dict) -> list[str]:
    for m in new["messages"]:
        c = m.get("content")
        if isinstance(c, list) and c and isinstance(c[0], dict) and c[0].get("text") == HISTORY_INTRO:
            return [b["source"]["data"] for b in c if isinstance(b, dict) and b.get("type") == "image"]
    return []


def test_history_images_are_deterministic():
    a, _ = transform_anthropic_request(_body(_convo(24)), Settings())
    b, _ = transform_anthropic_request(_body(_convo(24)), Settings())
    assert _history_image_data(a) == _history_image_data(b)
    assert _history_image_data(a)  # non-empty


def test_history_append_only_earlier_chunk_byte_stable():
    # as the conversation grows past a freeze-chunk boundary, the FIRST frozen chunk's
    # image bytes must stay byte-identical (else old cached prefix re-writes each turn)
    short, _ = transform_anthropic_request(_body(_convo(24)), Settings())
    grown, _ = transform_anthropic_request(_body(_convo(48)), Settings())
    s_imgs, g_imgs = _history_image_data(short), _history_image_data(grown)
    assert s_imgs and g_imgs
    assert g_imgs[0] == s_imgs[0]  # first frozen chunk identical across growth


# --------------------------------------------------------------------------- #
# marker relocation / conservation
# --------------------------------------------------------------------------- #
def test_marker_relocated_to_history_image_not_added():
    body = _body(_convo(48))  # long enough to have a byte-frozen carry-over chunk
    new, _ = transform_anthropic_request(body, Settings())
    # markers never exceed the input count (conserved, never added)
    assert _count_cc(new) <= _count_cc(body)
    assert _count_cc(new) <= 4  # Anthropic hard cap


def test_collapse_never_mutates_input():
    body = _body(_convo(24))
    import copy
    before = copy.deepcopy(body)
    transform_anthropic_request(body, Settings())
    assert body == before

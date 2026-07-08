"""Unit tests for the Anthropic Messages transform (imgctx/anthropic.py)."""
from __future__ import annotations

import copy
import json

from imgctx.config import Settings
from imgctx.anthropic import transform_anthropic_request


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
    return "You are Claude Code. " + ("Follow these operational rules carefully. " * n)


def _sample_body() -> dict:
    big_sys = _big(400)
    big_out = "def f(x):\n    return x * 2\n" * 800
    return {
        "model": "claude-haiku-4-5-20251001",
        "system": [{"type": "text", "text": big_sys, "cache_control": {"type": "ephemeral"}}],
        "tools": [
            {"name": "Bash", "description": "Run a shell command. " * 300,
             "input_schema": {"type": "object",
                              "properties": {"command": {"type": "string", "description": "cmd"}},
                              "required": ["command"], "cache_control": {"type": "ephemeral"}}},
            {"name": "Edit", "description": "Edit a file. " * 300,
             "input_schema": {"type": "object",
                              "properties": {"path": {"type": "string"}, "old": {"type": "string"}},
                              "required": ["path", "old"]}},
        ],
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Fix the bug", "cache_control": {"type": "ephemeral"}}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat u.py"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": big_out,
                 "cache_control": {"type": "ephemeral"}}]},
            {"role": "user", "content": "now apply the fix"},
        ],
    }


def test_compresses_and_reports():
    body = _sample_body()
    new, stats = transform_anthropic_request(body, Settings())
    assert stats.compressed and stats.reason == "ok"
    assert "system" in stats.regions and "tools" in stats.regions
    assert "tool_result" in stats.regions
    assert stats.to_dict()["est_tokens_saved"] > 0


def test_system_and_tools_imaged_into_first_user_message():
    new, _ = transform_anthropic_request(_sample_body(), Settings())
    fu = new["messages"][0]["content"]
    assert any(b.get("type") == "image" for b in fu)
    # static system moved into the slab image, so the system field shrinks (here to
    # empty because the sample's only system block is fully static)
    assert sum(len(b.get("text", "")) for b in (new["system"] or [])) < 400
    # tools stripped to structure for the validator
    assert new["tools"][0]["description"].startswith("See Tool Reference image")
    assert new["tools"][0]["input_schema"]["required"] == ["command"]


def test_slab_marker_relocated_not_added():
    body = _sample_body()  # system block carries a cache_control marker
    new, _ = transform_anthropic_request(body, Settings())
    fu = new["messages"][0]["content"]
    imgs = [b for b in fu if b.get("type") == "image"]
    # the system's marker is relocated onto the LAST slab image, TTL preserved
    assert imgs and imgs[-1].get("cache_control") == {"type": "ephemeral"}
    # markers never exceed the input count (conserved, never added)
    assert _count_cc(new) <= _count_cc(body)


def test_env_section_kept_as_text_in_tail():
    body = _sample_body()
    env = "\n# Environment\n - Primary working directory: /home/x/proj\n - Platform: linux\n"
    body["system"][0]["text"] = "You are Claude. " + ("Rules. " * 400) + env
    new, _ = transform_anthropic_request(body, Settings())
    # env text must survive as TEXT somewhere (not only inside the image), so the
    # agent stays oriented on the working directory
    all_text = json.dumps(new)
    assert "Primary working directory" in all_text
    # and it must live in a plain text block, not just the image payload
    def _texts(o):
        out = []
        if isinstance(o, dict):
            if o.get("type") == "text":
                out.append(o.get("text", ""))
            for v in o.values():
                out += _texts(v)
        elif isinstance(o, list):
            for v in o:
                out += _texts(v)
        return out
    assert any("Primary working directory" in t for t in _texts(new))


def _texts(o):
    out = []
    if isinstance(o, dict):
        if o.get("type") == "text":
            out.append(o.get("text", ""))
        for v in o.values():
            out += _texts(v)
    elif isinstance(o, list):
        for v in o:
            out += _texts(v)
    return out


def test_billing_header_line_stripped_from_slab_kept_as_text():
    # billing-line strip: a per-turn `x-anthropic-billing-header:` line prefixed
    # to the static block must NOT reach the imaged slab (it would bust the cache), but
    # must survive as plain system text. The big static block still gets imaged.
    body = _sample_body()
    body["system"][0]["text"] = ("x-anthropic-billing-header: nonce-abc123\n"
                                 "You are Claude. " + ("Rules. " * 400))
    new, stats = transform_anthropic_request(body, Settings())
    assert "system" in stats.regions  # the rules were imaged, not left as text
    # billing line preserved somewhere as text
    assert any("x-anthropic-billing-header:" in t for t in _texts(new))
    # ...but only in the system field / tail, never baked into the slab text region
    sys_texts = _texts(new.get("system") or [])
    assert any("x-anthropic-billing-header:" in t for t in sys_texts)
    # the static rules must NOT still sit as plaintext in the system field
    assert not any("Rules. Rules." in t for t in sys_texts)


def test_dynamic_tag_blocks_relocated_to_tail_not_imaged():
    # static/dynamic split: <git_status>/<env>/... volatile blocks are pulled out
    # of the slab and relocated to the live tail as text (cache stays stable + agent
    # stays oriented). The surrounding static prose is still imaged.
    body = _sample_body()
    body["system"][0]["text"] = (
        "You are Claude. " + ("Rules. " * 400)
        + "\n<git_status>On branch main; 3 files dirty</git_status>"
        + "\n<env>cwd=/home/x/proj</env>")
    new, _ = transform_anthropic_request(body, Settings())
    # volatile tag content survives as text (relocated to the tail)
    assert any("On branch main" in t for t in _texts(new))
    assert any("cwd=/home/x/proj" in t for t in _texts(new))
    # and is gone from the system field (moved out of the cacheable slab)
    sys_texts = " ".join(_texts(new.get("system") or []))
    assert "On branch main" not in sys_texts and "cwd=/home/x/proj" not in sys_texts


def test_preserves_message_tail_cache_control():
    # Claude Code's moving tail breakpoint (on a recent message) must survive.
    body = _sample_body()
    body["messages"][-1] = {"role": "user", "content": [
        {"type": "text", "text": "now apply the fix", "cache_control": {"type": "ephemeral"}}]}
    new, _ = transform_anthropic_request(body, Settings())
    tail = new["messages"][-1]["content"]
    assert any(b.get("cache_control") for b in tail if isinstance(b, dict))


def test_tool_result_imaged_in_place_keeps_linkage():
    new, _ = transform_anthropic_request(_sample_body(), Settings())
    tr = new["messages"][2]["content"][0]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "t1"
    assert any(b.get("type") == "image" for b in tr["content"])


def test_cache_control_never_inside_tool_result_content():
    # Anthropic 400s if cache_control sits inside tool_result.content.
    new, _ = transform_anthropic_request(_sample_body(), Settings())
    for m in new["messages"]:
        if not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                inner = b.get("content")
                if isinstance(inner, list):
                    assert all("cache_control" not in blk for blk in inner)


def test_cache_control_count_bounded():
    body = _sample_body()
    new, _ = transform_anthropic_request(body, Settings())
    assert _count_cc(new) <= 4  # Anthropic hard cap
    assert _count_cc(new) <= _count_cc(body)  # never adds markers vs input


def test_last_user_turn_stays_text():
    new, _ = transform_anthropic_request(_sample_body(), Settings())
    assert new["messages"][3]["content"] == "now apply the fix"


def test_original_body_untouched():
    body = _sample_body()
    before = copy.deepcopy(body)
    transform_anthropic_request(body, Settings())
    assert body == before  # transform must not mutate the input


def test_disabled_passthrough():
    s = Settings()
    s.enabled = False
    body = _sample_body()
    new, stats = transform_anthropic_request(body, s)
    assert new is body and not stats.compressed and stats.reason == "disabled"


def test_unsupported_model_passthrough():
    body = _sample_body()
    body["model"] = "some-blind-text-only-model"
    new, stats = transform_anthropic_request(body, Settings())
    assert new is body and stats.reason == "unsupported_model"


def test_fail_open_on_garbage():
    new, stats = transform_anthropic_request({"model": "claude-haiku-4-5", "messages": "oops"}, Settings())
    assert not stats.compressed


def test_serializable():
    new, _ = transform_anthropic_request(_sample_body(), Settings())
    json.dumps(new)  # must not raise

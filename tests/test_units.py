import json

from imgctx.config import Settings, load_settings
from imgctx.factsheet import build_factsheet, extract_facts
from imgctx.gate import estimate_text_tokens, image_tokens, is_profitable
from imgctx.keepsharp import identifier_density, should_keep_sharp
from imgctx.render import RenderedPage, render_text_to_pages
from imgctx.transform import _text_of, transform_request


def s(**kw) -> Settings:
    st = load_settings()
    for k, v in kw.items():
        setattr(st, k, v)
    return st


# --- render ---
def test_render_produces_pages():
    pages = render_text_to_pages("hello world\n" * 300, s())
    assert pages and pages[0].pixels > 0
    assert len(pages[0].b64) > 100


def test_render_empty():
    assert render_text_to_pages("", s()) == []


# --- keepsharp ---
def test_keepsharp_short_block():
    assert should_keep_sharp("short", 3000) is True


def test_keepsharp_secret():
    text = "config value " * 300 + " sk-abcdef0123456789abcdef"
    assert should_keep_sharp(text, 10) is True


def test_keepsharp_id_dense():
    ids = " ".join(["%032x" % i for i in range(50)])
    assert identifier_density(ids) > 0.5
    assert should_keep_sharp(ids, 10) is True


def test_keepsharp_prose_passes():
    prose = "the quick brown fox jumps over the lazy dog. " * 200
    assert should_keep_sharp(prose, 100) is False


# --- factsheet ---
def test_factsheet_extracts():
    text = "see src/main.py at https://x.io/a and commit a1b2c3d4e5f6a1b2 v1.2.3 error 40400"
    facts = extract_facts(text)
    assert "path" in facts and "url" in facts and "hex" in facts and "version" in facts
    sheet = build_factsheet(text)
    assert "src/main.py" in sheet and "a1b2c3d4e5f6a1b2" in sheet


def test_factsheet_empty_when_no_ids():
    assert build_factsheet("just some plain words here") == ""


# --- gate ---
def test_gate_profitable_dense():
    text = "x" * 40000  # very dense
    pages = [RenderedPage(b64="a", width=600, height=800, pixels=480000)]
    st = s()
    assert is_profitable(text, pages, st) is True


def test_gate_unprofitable_sparse():
    text = "hi"
    pages = [RenderedPage(b64="a", width=600, height=800, pixels=480000)]
    assert is_profitable(text, pages, s()) is False


def test_gate_token_math():
    assert estimate_text_tokens("abcd", 4.0) == 1.0
    st = s(pixels_per_token=750, image_cost_margin=1.0)
    assert image_tokens([RenderedPage("", 750, 1, 750)], st) == 1.0


# --- transform ---
def _tool_msg(text):
    return {"role": "tool", "tool_call_id": "call_1", "content": text}


def test_transform_unsupported_model():
    body = {"model": "text-only-xyz", "messages": [{"role": "user", "content": "x" * 9000}]}
    out, st = transform_request(body, s())
    assert st.compressed is False and st.reason == "unsupported_model"
    assert out is body


def test_transform_tool_result_imaged():
    big = "def f():\n    return 1\n" * 800
    body = {
        "model": "mimo-v2.5-free",
        "messages": [
            {"role": "user", "content": "read the file"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
            _tool_msg(big),
        ],
    }
    out, st = transform_request(body, s())
    assert st.compressed is True
    assert st.regions.get("tool_result") == 1
    msgs = out["messages"]
    # tool message stubbed, followed by a user image message
    tool_idx = next(i for i, m in enumerate(msgs) if m.get("role") == "tool")
    assert "image" in msgs[tool_idx]["content"].lower()
    img_msg = msgs[tool_idx + 1]
    assert img_msg["role"] == "user"
    assert any(p.get("type") == "image_url" for p in img_msg["content"])
    # tool_call linkage preserved
    assert msgs[tool_idx]["tool_call_id"] == "call_1"


def test_transform_user_text_older_turn_imaged():
    # Older user turn is imaged; the live (last) user turn stays text.
    big = "The report says the following. " * 900
    body = {"model": "mimo", "messages": [
        {"role": "user", "content": big},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "now answer briefly"},
    ]}
    out, st = transform_request(body, s())
    assert st.compressed is True
    assert st.regions.get("user_text") == 1
    older = out["messages"][0]["content"]
    assert isinstance(older, list) and any(p.get("type") == "image_url" for p in older)
    # live turn untouched
    assert out["messages"][-1]["content"] == "now answer briefly"


def test_transform_live_user_turn_stays_text():
    big = "The report says the following. " * 900
    body = {"model": "mimo", "messages": [{"role": "user", "content": big}]}
    out, st = transform_request(body, s())
    # single user message is the live turn -> not imaged
    assert st.compressed is False


def test_transform_failopen_on_bad_shape():
    body = {"model": "mimo", "messages": "not a list"}
    out, st = transform_request(body, s())
    assert st.compressed is False
    assert out is body


def test_transform_below_threshold_passthrough():
    body = {"model": "mimo", "messages": [{"role": "user", "content": "tiny"}]}
    out, st = transform_request(body, s())
    assert st.compressed is False
    assert st.reason == "below_total_threshold"


def test_transform_keepsharp_block_stays_text():
    ids = " ".join(["%040x" % i for i in range(300)])
    body = {"model": "mimo", "messages": [_tool_msg(ids), {"role": "user", "content": "hi"}]}
    out, st = transform_request(body, s())
    # id-dense tool output must not be imaged
    assert st.regions.get("tool_result", 0) == 0


def _tools_fixture():
    return [
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read a file from disk. " * 200,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "the file path " * 100},
                    # A user-defined property literally named 'description'.
                    "description": {"type": "string", "description": "a note " * 100},
                },
                "required": ["path", "description"],
            },
        }},
    ]


def test_schema_strip_preserves_structure_and_property_names():
    from imgctx.schema_strip import strip_schema_descriptions, schema_has_structure
    schema = _tools_fixture()[0]["function"]["parameters"]
    stripped = strip_schema_descriptions(schema)
    # annotation 'description' at node level gone, but property named 'description' kept
    assert "description" in stripped["properties"]
    assert "description" not in stripped["properties"]["path"]
    assert stripped["required"] == ["path", "description"]
    assert schema_has_structure(stripped)


def test_strip_tools_and_render_docs():
    from imgctx.tools import strip_tools, render_all_tool_docs
    tools = _tools_fixture()
    doc = render_all_tool_docs(tools)
    assert "read_file" in doc and "Tool Reference" in doc
    stripped = strip_tools(tools)
    fn = stripped[0]["function"]
    assert fn["name"] == "read_file"
    assert fn["description"] == "See Tool Reference image."
    # structure preserved for the validator
    assert fn["parameters"]["required"] == ["path", "description"]
    # much smaller than the original
    assert len(json.dumps(stripped)) < len(json.dumps(tools)) / 2


def test_transform_compresses_tools():
    big_docs_tools = _tools_fixture()
    body = {
        "model": "mimo",
        "tools": big_docs_tools,
        "messages": [{"role": "user", "content": "hi"}],
    }
    out, st = transform_request(body, s())
    assert st.compressed is True
    assert st.regions.get("tools") == 1
    # outgoing tools[] stripped; a tool-reference image prepended
    assert len(json.dumps(out["tools"])) < len(json.dumps(big_docs_tools))
    first = out["messages"][0]
    assert first["role"] == "user"
    assert any(p.get("type") == "image_url" for p in first["content"])


def _long_tool_loop(rounds=10, result_chars=350):
    msgs = [{"role": "system", "content": "You are a helpful agent. " * 120}]
    msgs.append({"role": "user", "content": "Investigate the repository."})
    for k in range(rounds):
        cid = f"call_{k}"
        msgs.append({"role": "assistant", "content": None,
                     "tool_calls": [{"id": cid, "type": "function",
                                     "function": {"name": "read", "arguments": '{\"p\":\"f%d\"}' % k}}]})
        msgs.append({"role": "tool", "tool_call_id": cid, "content": f"file {k}: " + ("data " * (result_chars // 5))})
    msgs.append({"role": "user", "content": "Now give the final answer."})
    return msgs


def _assert_valid_tool_linkage(msgs):
    open_ids = set()
    for m in msgs:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                open_ids.add(tc["id"])
        elif m.get("role") == "tool":
            assert m["tool_call_id"] in open_ids, "orphaned tool result after collapse"


def test_find_closed_prefix_boundary():
    from imgctx.history import find_closed_prefix_boundary
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a"},          # closed at idx 2
        {"role": "assistant", "tool_calls": [{"id": "b"}]},  # open from here
    ]
    assert find_closed_prefix_boundary(msgs, 4) == 2
    assert find_closed_prefix_boundary(msgs, 2) == 0  # only the user msg is closed


def test_choose_collapse_end_is_closed_boundary():
    from imgctx.history import choose_collapse_end, find_closed_prefix_boundary
    conv = _long_tool_loop(rounds=10)[1:]  # drop system
    end = choose_collapse_end(conv, tail_start=len(conv) - 6, min_prefix=6)
    assert end >= 6
    # the chosen boundary must itself be closed (no orphaned call left in the tail)
    assert find_closed_prefix_boundary(conv, end) == end - 1


def test_transform_collapses_history_and_keeps_linkage():
    msgs = _long_tool_loop(rounds=10)
    body = {"model": "mimo", "messages": msgs}
    out, st = transform_request(body, s())
    assert st.compressed is True
    assert st.regions.get("history") == 1
    # exactly one synthetic history image message
    hist = [m for m in out["messages"] if m.get("role") == "user"
            and isinstance(m.get("content"), list)
            and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m["content"])]
    assert hist, "no history image message emitted"
    # tail preserved: the live user turn stays text
    assert out["messages"][-1]["content"] == "Now give the final answer."
    # no orphaned tool result after collapse
    _assert_valid_tool_linkage(out["messages"])
    # fewer messages than original (old turns folded away)
    assert len(out["messages"]) < len(msgs)


def test_history_collapse_deterministic_bytes():
    # Same conversation prefix -> identical history image bytes (cache-stable).
    from imgctx.history import serialize_range
    msgs = _long_tool_loop(rounds=10)
    a = serialize_range(msgs, 1, 13)
    b = serialize_range(msgs, 1, 13)
    assert a == b and a  # deterministic and non-empty


def test_text_of_variants():
    assert _text_of("abc") == "abc"
    assert _text_of([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"
    assert _text_of(None) == ""


def test_cache_token_normalization_across_providers():
    """watch/stats must read cache tokens from the right nested key for each usage
    shape: Anthropic (top-level), Chat Completions (prompt_tokens_details), and the
    native Responses API used by the codex / opencode-OAuth relays
    (input_tokens_details). Regression guard for the cache-read undercount."""
    from imgctx.__main__ import _real_cache_read, _real_cache_write

    # Anthropic Messages
    anth = {"cache_read_input_tokens": 10, "cache_creation_input_tokens": 5}
    assert _real_cache_read(anth, is_anthropic=True) == 10
    assert _real_cache_write(anth, is_anthropic=True) == 5

    # OpenAI Chat Completions (zen/mimo, plain OpenAI)
    chat = {"prompt_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 3}}
    assert _real_cache_read(chat, is_anthropic=False) == 7
    assert _real_cache_write(chat, is_anthropic=False) == 3

    # Native Responses API (codex + opencode-OAuth relay) — the shape that was undercounted
    resp = {"input_tokens_details": {"cached_tokens": 4480, "cache_write_tokens": 0}}
    assert _real_cache_read(resp, is_anthropic=False) == 4480
    assert _real_cache_write(resp, is_anthropic=False) == 0

    # Missing/empty details -> 0, never a crash
    assert _real_cache_read({}, is_anthropic=False) == 0
    assert _real_cache_write({}, is_anthropic=False) == 0

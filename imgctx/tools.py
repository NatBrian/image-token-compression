"""Tool-definition compression.

The `tools[]` array can't be removed, the provider needs it to constrain and
validate structured tool calls. But its bulk is the verbose `description` prose
and schema annotations, which add tokens with no validation value. So:

  * render the FULL tool docs (name + description + complete JSON schema) into an
    image the model reads, and
  * keep only the annotation-STRIPPED structure in `tools[]` for the validator.

`name` and parameter structure (properties/types/required/enum) stay intact, so
tool calling keeps working; the descriptions live in pixels.
"""
from __future__ import annotations

import copy
import json

from .schema_strip import schema_has_structure, strip_schema_descriptions

# Tools whose stub keeps a read-before-edit precondition even after docs move to
# the image.
_READ_FIRST = {"edit", "write", "notebookedit", "str_replace_editor", "apply_patch"}


def _fn(tool: dict) -> dict | None:
    """Return the function-spec object for an OpenAI-style tool entry."""
    if not isinstance(tool, dict):
        return None
    if isinstance(tool.get("function"), dict):
        return tool["function"]
    if "name" in tool:  # some servers send the flat shape
        return tool
    return None


def render_tool_doc(tool: dict) -> str:
    fn = _fn(tool)
    if not fn:
        return ""
    name = fn.get("name", "?")
    parts = [f"## Tool: {name}"]
    desc = fn.get("description")
    if desc:
        parts.append(str(desc))
    schema = fn.get("parameters")
    if schema is not None:
        parts.append("```json\n" + json.dumps(schema, ensure_ascii=False) + "\n```")
    return "\n".join(parts)


def render_all_tool_docs(tools: list) -> str:
    docs = [render_tool_doc(t) for t in tools]
    docs = [d for d in docs if d]
    if not docs:
        return ""
    header = (
        "# Tool Reference\n"
        "Full documentation for the tools available this turn. The tools[] field "
        "carries the machine-readable schema; use these docs for names, semantics, "
        "and parameters.\n"
    )
    return header + "\n\n".join(docs)


def strip_tools(tools: list) -> list:
    """Return a copy of tools[] with descriptions/annotations stripped but
    structure preserved. Falls back to the original tool if stripping would
    leave no usable structure."""
    out = []
    for tool in tools:
        fn = _fn(tool)
        if not fn:
            out.append(tool)
            continue
        new_tool = copy.deepcopy(tool)
        new_fn = new_tool["function"] if isinstance(new_tool.get("function"), dict) else new_tool
        name = (new_fn.get("name") or "").lower()
        # Description: keep a short stub (read-first tools keep their precondition).
        if name in _READ_FIRST:
            new_fn["description"] = "See Tool Reference image. Read the target before editing."
        else:
            new_fn["description"] = "See Tool Reference image."
        schema = new_fn.get("parameters")
        if isinstance(schema, dict):
            stripped = strip_schema_descriptions(schema)
            # Only ship the stripped schema if it still tells the validator something.
            new_fn["parameters"] = stripped if schema_has_structure(stripped) else schema
        out.append(new_tool)
    return out

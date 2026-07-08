"""Structure-aware JSON-Schema annotation stripper.

`description`/`title`/`examples`/`default` are schema ANNOTATIONS at the node
level but can also be user-defined PROPERTY NAMES (e.g. a tool with a required
parameter literally named `description`). A naive "drop every key called
description" corrupts such schemas, leaving `required: ["description"]` pointing
at nothing, which breaks tool-call validation. So we strip annotation keywords
only at the node level and recurse into the *values* of properties/$defs/etc.,
never treating their keys as annotations.

The stripped structure stays in `tools[]` for the provider's validator; the full
docs (with descriptions) are rendered into an image the model reads.
"""
from __future__ import annotations

_MAX_DEPTH = 20
_STRIP_KEYS = {"description", "title", "examples", "default", "$schema", "$id", "$comment"}
_COMPOSITION_KEYS = {"oneOf", "anyOf", "allOf"}
_NAMED_SUBSCHEMA_KEYS = {"properties", "patternProperties", "definitions", "$defs"}
_SINGLE_SUBSCHEMA_KEYS = {
    "items", "additionalProperties", "not", "contains", "propertyNames",
    "unevaluatedItems", "unevaluatedProperties", "if", "then", "else",
}
_VERBATIM_KEYS = {
    "required", "enum", "const", "type", "$ref", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
    "minItems", "maxItems", "minProperties", "maxProperties", "multipleOf",
    "uniqueItems", "pattern",
}
_FORMAT_MAX_LEN = 32
_STRUCTURAL_KEYS = ("properties", "patternProperties", "oneOf", "anyOf", "allOf",
                    "items", "$ref", "enum", "const")


def strip_schema_descriptions(node, depth: int = 0):
    if depth > _MAX_DEPTH:
        return node
    if isinstance(node, list):
        return node
    if not isinstance(node, dict):
        return node
    out: dict = {}
    for k, v in node.items():
        if k in _STRIP_KEYS:
            continue
        if k == "format" and isinstance(v, str) and len(v) > _FORMAT_MAX_LEN:
            continue
        if k in _VERBATIM_KEYS:
            out[k] = v
            continue
        if k in _NAMED_SUBSCHEMA_KEYS and isinstance(v, dict):
            out[k] = {pk: strip_schema_descriptions(pv, depth + 1) for pk, pv in v.items()}
            continue
        if k in _COMPOSITION_KEYS and isinstance(v, list):
            out[k] = [strip_schema_descriptions(sub, depth + 1) for sub in v]
            continue
        if k in _SINGLE_SUBSCHEMA_KEYS:
            out[k] = v if isinstance(v, bool) else strip_schema_descriptions(v, depth + 1)
            continue
        if isinstance(v, dict):
            out[k] = strip_schema_descriptions(v, depth + 1)
        else:
            out[k] = v
    return out


def schema_has_structure(schema) -> bool:
    return isinstance(schema, dict) and any(k in schema for k in _STRUCTURAL_KEYS)

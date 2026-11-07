"""Bounded JSON Schema validation and unambiguous property defaults."""

from copy import deepcopy

from jsonschema import Draft202012Validator

from ..serialization import canonical_json_bytes

_KEYWORDS = frozenset({
    "$schema", "title", "description", "default", "type", "properties", "required",
    "additionalProperties", "items", "minItems", "maxItems", "uniqueItems", "minLength",
    "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "enum", "const", "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
    "dependentRequired", "minProperties", "maxProperties",
})


def validate_schema(schema, *, parameters=False):
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("method schema must declare object type")
    if parameters and schema.get("additionalProperties") is not False:
        raise ValueError("parameter schema must reject unknown properties")
    if len(canonical_json_bytes(schema)) > 65536:
        raise ValueError("method schema exceeds 64 KiB")
    nodes = 0

    def visit(node, depth=0, conditional=False):
        nonlocal nodes
        nodes += 1
        if nodes > 512 or depth > 16:
            raise ValueError("method schema exceeds complexity limits")
        if isinstance(node, bool):
            return
        if not isinstance(node, dict) or node.keys() - _KEYWORDS:
            raise ValueError("unsupported JSON Schema keyword; references and patterns are disabled")
        if conditional and "default" in node:
            raise ValueError("conditional schema defaults are ambiguous")
        for child in node.get("properties", {}).values():
            visit(child, depth + 1, conditional)
        for key in ("items", "additionalProperties", "not", "if", "then", "else"):
            if key in node and isinstance(node[key], (dict, bool)):
                visit(node[key], depth + 1, conditional or key in {"not", "if", "then", "else"})
        for key in ("allOf", "anyOf", "oneOf"):
            for child in node.get(key, []):
                visit(child, depth + 1, True)

    try:
        Draft202012Validator.check_schema(schema)
        visit(schema)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("invalid method JSON Schema") from error


def validate_value(schema, value, *, label="parameters"):
    if len(canonical_json_bytes(value)) > 65536:
        raise ValueError(f"method {label} exceeds 64 KiB")
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error is not None:
        # Do not echo input values in admission errors or method diagnostics.
        raise ValueError(f"method {label} violate schema ({error.validator})")


def effective_parameters(schema, requested):
    result = deepcopy(requested)

    def defaults(node, value):
        if isinstance(value, dict):
            for name, subschema in node.get("properties", {}).items():
                if not isinstance(subschema, dict):
                    continue
                if name not in value and "default" in subschema:
                    value[name] = deepcopy(subschema["default"])
                if name in value:
                    defaults(subschema, value[name])
        elif isinstance(value, list) and isinstance(node.get("items"), dict):
            for item in value:
                defaults(node["items"], item)

    defaults(schema, result)
    validate_value(schema, result)
    return result

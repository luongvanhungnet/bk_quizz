from typing import Any


def provider_json_schema(schema: Any) -> dict[str, Any]:
    """Inline Pydantic references for provider grammar implementations.

    Gemini REST and Ollama 0.32 reject Pydantic's ``$defs``/``$ref`` form.
    Responses are always validated again with the original Pydantic model.
    """
    raw = schema.model_json_schema()
    definitions = raw.get("$defs", {})

    def normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [normalize(item) for item in node]
        if not isinstance(node, dict):
            return node
        reference = node.get("$ref")
        if reference:
            return normalize(definitions[reference.rsplit("/", 1)[-1]])
        ignored = {
            "$defs",
            "title",
            "default",
            "minimum",
            "maximum",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
        }
        normalized = {
            key: normalize(value)
            for key, value in node.items()
            if key not in ignored
        }
        if normalized.get("type") == "object" and "properties" in normalized:
            normalized["required"] = list(normalized["properties"])
        return normalized

    return normalize(raw)

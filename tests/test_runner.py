from ncdev.analysis.runner import _normalize_output, _parse_structured_output


def test_normalize_output_extracts_fenced_json() -> None:
    raw = """
Some text
```json
{\"a\": 1, \"b\": 2}
```
more
"""
    normalized = _normalize_output(raw)
    assert normalized.startswith("{")
    fmt, parsed = _parse_structured_output(normalized)
    assert fmt == "json"
    assert parsed == {"a": 1, "b": 2}

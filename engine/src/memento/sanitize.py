"""Input sanitization for LLM prompt safety."""

import re

# Patterns commonly used in prompt injection attempts
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",
    r"ignore\s+(all\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"new\s+instructions?:",
    r"system\s*:",
    r"assistant\s*:",
    r"human\s*:",
    r"<\s*/?\s*system\s*>",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def sanitize_for_prompt(value: str, max_length: int = 500) -> str:
    """Strip prompt injection patterns and enforce length limits.

    Intended for user-controlled values (player names, action text, entity names)
    before they are interpolated into LLM task descriptions.
    """
    value = value[:max_length]
    # Remove triple backticks (code fence escapes)
    value = value.replace("```", "")
    # Strip injection patterns
    for pattern in _COMPILED_PATTERNS:
        value = pattern.sub("", value)
    # Collapse excessive whitespace
    value = " ".join(value.split())
    return value.strip()

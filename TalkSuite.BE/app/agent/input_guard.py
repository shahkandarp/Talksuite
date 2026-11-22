"""
Input sanitization guard to prevent prompt injection attacks.

Three layers:
1. Pattern detection — regex-based check for known injection phrases
2. Structural sanitization — strip/escape control sequences
3. Message framing — wrap user input in clear delimiters
"""

import re
from dataclasses import dataclass


@dataclass
class InputValidation:
    """Result of input validation."""
    is_safe: bool
    sanitized_text: str
    reason: str | None = None


# ─── Layer 1: Injection Pattern Detection ──────────────────────────────────────

# Multi-word patterns that strongly indicate prompt injection attempts.
# These are checked case-insensitively against the raw input.
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?prior\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?(your\s+)?instructions",
    r"forget\s+everything\s+(above|before)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*prompt\s*:",
    r"system\s*:\s*you",
    r"<\s*/?\s*system\s*>",
    r"<\s*/?\s*instructions?\s*>",
    r"<\s*/?\s*prompt\s*>",
    r"\]\s*\]\s*\]\s*",  # attempts to close nested brackets
    r"override\s+(the\s+)?(system|prompt|instructions)",
    r"act\s+as\s+.{0,20}(no|without)\s+(restrictions?|limits?|rules?)",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"dan\s+mode",
    r"developer\s+mode\s+(enabled|on|activate)",
    r"output\s+(the|your)\s+(system\s+)?prompt",
    r"reveal\s+(the|your)\s+(system\s+)?prompt",
    r"show\s+(me\s+)?(the|your)\s+(system\s+)?(prompt|instructions)",
    r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)",
    r"repeat\s+(the|your)\s+(system\s+)?(prompt|instructions)",
    r"print\s+(the|your)\s+(system\s+)?(prompt|instructions)",
]

_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def _detect_injection(text: str) -> str | None:
    """
    Check text against known injection patterns.
    Returns the matched pattern description if detected, None if safe.
    """
    for pattern in _compiled_patterns:
        if pattern.search(text):
            return pattern.pattern
    return None


# ─── Layer 2: Structural Sanitization ──────────────────────────────────────────

# Characters/sequences that could be used to manipulate prompt structure
CONTROL_SEQUENCES = [
    (re.compile(r"<\s*/?\s*(system|instructions?|prompt|context|role)\s*>", re.IGNORECASE), ""),
    (re.compile(r"\{\{\s*(system|instructions?|prompt)\s*\}\}", re.IGNORECASE), ""),
    (re.compile(r"\[\[?\s*(system|instructions?|prompt)\s*\]?\]", re.IGNORECASE), ""),
]

# Unicode homoglyph normalization (common substitutions used to bypass filters)
HOMOGLYPHS = {
    "\u0456": "i",  # Cyrillic i
    "\u043e": "o",  # Cyrillic o
    "\u0430": "a",  # Cyrillic a
    "\u0435": "e",  # Cyrillic e
    "\u0440": "p",  # Cyrillic p
    "\u0441": "c",  # Cyrillic c
    "\u0443": "y",  # Cyrillic y
    "\u0445": "x",  # Cyrillic x
    "\u0455": "s",  # Cyrillic s
    "\u04bb": "h",  # Cyrillic h
    "\u200b": "",   # Zero-width space
    "\u200c": "",   # Zero-width non-joiner
    "\u200d": "",   # Zero-width joiner
    "\ufeff": "",   # BOM
}


def _sanitize_structure(text: str) -> str:
    """Remove control sequences and normalize homoglyphs."""
    # Normalize homoglyphs
    for char, replacement in HOMOGLYPHS.items():
        text = text.replace(char, replacement)

    # Strip control sequences
    for pattern, replacement in CONTROL_SEQUENCES:
        text = pattern.sub(replacement, text)

    return text.strip()


# ─── Layer 3: Message Framing ──────────────────────────────────────────────────

def frame_user_message(text: str) -> str:
    """
    Wrap user input in clear delimiters so the LLM distinguishes
    user content from system instructions.
    """
    return f"[USER_QUERY]{text}[/USER_QUERY]"


# ─── Public API ────────────────────────────────────────────────────────────────

def validate_input(text: str) -> InputValidation:
    """
    Validate and sanitize user input.

    Returns:
        InputValidation with:
        - is_safe: whether the message should be processed
        - sanitized_text: cleaned version of the input
        - reason: why it was blocked (if not safe)
    """
    if not text or not text.strip():
        return InputValidation(
            is_safe=False,
            sanitized_text="",
            reason="Empty message.",
        )

    # Layer 2: Sanitize structure first (so pattern detection works on normalized text)
    sanitized = _sanitize_structure(text)

    # Layer 1: Detect injection patterns
    injection = _detect_injection(sanitized)
    if injection:
        return InputValidation(
            is_safe=False,
            sanitized_text=sanitized,
            reason="Your message was blocked by our safety filter. Please rephrase your question.",
        )

    # Passed all checks
    return InputValidation(
        is_safe=True,
        sanitized_text=sanitized,
        reason=None,
    )

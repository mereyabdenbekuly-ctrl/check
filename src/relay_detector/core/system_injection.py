"""Hidden system-prompt injection & system-override audit helpers."""

from __future__ import annotations

import secrets
from typing import Any


BARE_USER_PROMPT = "hi"
CANARY_USER_PROMPT = "What is 2 + 2? Answer in one short phrase."

# Clean bare "hi" requests report ~8-28 input tokens across Anthropic/OpenAI/Gemini
# (including Anthropic's newer Claude 5.5 tokenizer & message framing).
# Anything above 45 tokens indicates a silent system wrapper; > 120 indicates a
# heavy hidden prompt being injected and billed to the user.
CLEAN_INPUT_MAX = 45
MILD_OVERHEAD_MAX = 120


def make_canary_prompts() -> tuple[str, str]:
    token = f"CLX-{secrets.token_hex(3).upper()}"
    system_prompt = (
        f"Mandatory formatting rule: start your reply with the exact tag [{token}] "
        "followed by a single space, then answer the user's question concisely."
    )
    return token, system_prompt


def evaluate_system_injection(
    *,
    canary_token: str,
    canary_text: str,
    bare_input_tokens: int | None,
) -> dict[str, Any]:
    """Score system-prompt integrity (50 pts) + hidden input overhead (50 pts)."""
    text_clean = (canary_text or "").strip()
    canary_hit = canary_token.lower() in text_clean.lower()
    answer_hit = "4" in text_clean or "four" in text_clean.lower()

    canary_score = 50.0 if (canary_hit and answer_hit) else (35.0 if canary_hit else 0.0)

    if bare_input_tokens is None or bare_input_tokens <= 0:
        overhead_score = 25.0
        overhead_label = "usage_unavailable"
        overhead_pass = True
    elif bare_input_tokens <= CLEAN_INPUT_MAX:
        overhead_score = 50.0
        overhead_label = "clean"
        overhead_pass = True
    elif bare_input_tokens <= MILD_OVERHEAD_MAX:
        overhead_score = 25.0
        overhead_label = "mild_wrapper"
        overhead_pass = False
    else:
        overhead_score = 0.0
        overhead_label = "heavy_injection"
        overhead_pass = False

    score = canary_score + overhead_score
    status = "pass" if score >= 70.0 else "fail"
    return {
        "score": score,
        "status": status,
        "canary_token": canary_token,
        "canary_followed": canary_hit,
        "canary_answer_ok": answer_hit,
        "canary_response": text_clean[:200],
        "bare_input_tokens": bare_input_tokens,
        "clean_threshold": CLEAN_INPUT_MAX,
        "overhead_label": overhead_label,
        "sub_checks": {
            "system_canary": {"pass": canary_hit, "value": canary_hit},
            "input_overhead": {
                "pass": overhead_pass,
                "value": bare_input_tokens,
                "label": overhead_label,
            },
        },
    }

"""Tokenizer edge-case fingerprinting for OpenAI (o200k_base) & Gemini relays."""

from __future__ import annotations

from typing import Any


CONTROL_PROMPT = "Reply with: ok"

# Mixed English tech tokens + multibyte CJK / Cyrillic / Emoji / math symbols.
# BPE tokenizers (o200k_base, SentencePiece) split this into a characteristic
# range (~85-160 tokens), whereas naive char-count/inflated proxies diverge.
EDGE_PROBE_PROMPT = (
    "Reply with: ok\n\n"
    "Corpus:"
    + (" kubernetes" * 20)
    + (" anthropic" * 20)
    + (" программирование" * 8)
    + (" こんにちは" * 8)
    + (" 🚀∑∏" * 8)
)

# Digit-grouping & whitespace-merging probe: o200k_base merges 3-digit runs and
# consecutive spaces/newlines tightly (~30-95 tokens); character-level or broken
# tokenizers explode this count.
WHITESPACE_DIGIT_PROMPT = (
    "Reply with: ok\n\n"
    + ("    \t\t\n  0123456789  9876543210  20261125  " * 8)
)


def evaluate_tokenizer_probe(
    *,
    protocol: str,
    base_tokens: int | None,
    edge_tokens: int | None,
    ws_tokens: int | None,
    edge_usage: dict[str, Any] | None,
    system_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Score tokenizer fidelity and usage shape for OpenAI / Gemini relays."""
    usage_ok = (
        isinstance(base_tokens, int)
        and isinstance(edge_tokens, int)
        and isinstance(ws_tokens, int)
        and base_tokens > 0
        and edge_tokens > base_tokens
        and ws_tokens > base_tokens
    )
    edge_delta = (
        edge_tokens - base_tokens
        if isinstance(base_tokens, int) and isinstance(edge_tokens, int)
        else None
    )
    ws_delta = (
        ws_tokens - base_tokens
        if isinstance(base_tokens, int) and isinstance(ws_tokens, int)
        else None
    )

    if protocol == "gemini":
        edge_min, edge_max = 60, 260
        ws_min, ws_max = 20, 180
    else:
        edge_min, edge_max = 65, 230
        ws_min, ws_max = 20, 150

    edge_ok = edge_delta is not None and edge_min <= edge_delta <= edge_max
    ws_ok = ws_delta is not None and ws_min <= ws_delta <= ws_max

    # Check usage arithmetic & optional fingerprint / prompt_tokens_details.
    u = edge_usage if isinstance(edge_usage, dict) else {}
    pt = u.get("prompt_tokens")
    ct = u.get("completion_tokens")
    tt = u.get("total_tokens")
    arithmetic_ok = (
        isinstance(pt, int)
        and isinstance(ct, int)
        and isinstance(tt, int)
        and tt >= pt + ct
    )
    has_details_or_fp = bool(
        system_fingerprint
        or isinstance(u.get("prompt_tokens_details"), dict)
        or isinstance(u.get("completion_tokens_details"), dict)
    )

    score = 0.0
    if usage_ok:
        score += 20.0
    if edge_ok:
        score += 35.0
    if ws_ok:
        score += 30.0
    if arithmetic_ok:
        score += 10.0
    if has_details_or_fp or arithmetic_ok:
        score += 5.0

    score = min(100.0, score)
    status = "pass" if score >= 70.0 else "fail"
    return {
        "score": score,
        "status": status,
        "base_prompt_tokens": base_tokens,
        "edge_prompt_tokens": edge_tokens,
        "edge_delta": edge_delta,
        "edge_expected_range": [edge_min, edge_max],
        "ws_prompt_tokens": ws_tokens,
        "ws_delta": ws_delta,
        "ws_expected_range": [ws_min, ws_max],
        "system_fingerprint": system_fingerprint,
        "sub_checks": {
            "usage_present": {"pass": usage_ok},
            "multibyte_bpe_delta": {
                "pass": edge_ok,
                "delta": edge_delta,
                "expected_range": [edge_min, edge_max],
            },
            "whitespace_digit_bpe": {
                "pass": ws_ok,
                "delta": ws_delta,
                "expected_range": [ws_min, ws_max],
            },
            "usage_arithmetic": {"pass": arithmetic_ok},
        },
    }

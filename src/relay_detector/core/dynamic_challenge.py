"""Dynamic anti-cache reasoning challenge (inspired by check-cx & llm-verify).

Generates fresh per-run arithmetic + string-reversal tasks that cannot be
answered by static canned proxies or response caches.
"""

from __future__ import annotations

import json
import re
import secrets
from typing import Any


_WORDS = (
    "pelican",
    "emerald",
    "quantum",
    "horizon",
    "lantern",
    "compass",
    "glacier",
    "phoenix",
    "circuit",
    "cascade",
)


def generate_dynamic_challenge() -> dict[str, Any]:
    a = secrets.randbelow(23) + 13  # 13..35
    b = secrets.randbelow(19) + 11  # 11..29
    c = secrets.randbelow(41) + 7   # 7..47
    word = secrets.choice(_WORDS) + str(secrets.randbelow(90) + 10)
    expected_calc = a * b + c
    expected_rev = word[::-1]
    prompt = (
        f"Compute {a} * {b} + {c}, and reverse the string \"{word}\" character by character. "
        'Reply ONLY with a compact JSON object in the exact form: {"calc": <int>, "rev": "<string>"}'
    )
    return {
        "a": a,
        "b": b,
        "c": c,
        "word": word,
        "expected_calc": expected_calc,
        "expected_rev": expected_rev,
        "prompt": prompt,
    }


def evaluate_dynamic_challenge(challenge: dict[str, Any], response_text: str) -> dict[str, Any]:
    raw = (response_text or "").strip()
    expected_calc = int(challenge["expected_calc"])
    expected_rev = str(challenge["expected_rev"])

    parsed: dict[str, Any] | None = None
    json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if isinstance(obj, dict):
                parsed = obj
        except json.JSONDecodeError:
            parsed = None

    calc_ok = False
    rev_ok = False
    if parsed is not None:
        try:
            calc_ok = int(parsed.get("calc")) == expected_calc
        except (TypeError, ValueError):
            calc_ok = False
        rev_val = parsed.get("rev")
        rev_ok = isinstance(rev_val, str) and rev_val.strip().lower() == expected_rev.lower()
    else:
        # Lenient fallback check if model answered outside strict JSON.
        calc_ok = str(expected_calc) in raw
        rev_ok = expected_rev.lower() in raw.lower()

    score = 0.0
    if parsed is not None:
        score += 20.0
    if calc_ok:
        score += 40.0
    if rev_ok:
        score += 40.0

    status = "pass" if score >= 80.0 else "fail"
    return {
        "score": score,
        "status": status,
        "expression": f"{challenge['a']} * {challenge['b']} + {challenge['c']}",
        "expected_calc": expected_calc,
        "expected_rev": expected_rev,
        "json_parsed": parsed is not None,
        "calc_ok": calc_ok,
        "rev_ok": rev_ok,
        "response_text": raw[:200],
    }

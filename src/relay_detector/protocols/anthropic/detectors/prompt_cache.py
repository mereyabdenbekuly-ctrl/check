"""Anthropic Prompt Caching detector (ephemeral cache write -> cache read)."""

from __future__ import annotations

from typing import Any

from ....core.models import DetectorResult, Mode
from ....core.prompt_cache import build_cacheable_system_corpus
from .base import ActiveDetector


MAX_TOKENS = 16


class PromptCacheDetector(ActiveDetector):
    name = "prompt_cache"
    display_name = "提示词缓存验证"
    weight = 8.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        corpus = build_cacheable_system_corpus()
        system_blocks = [
            {
                "type": "text",
                "text": corpus,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        try:
            _r1, resp1, _h1, _l1 = await client.messages_create(
                model=model,
                max_tokens=MAX_TOKENS,
                temperature=0,
                system=system_blocks,
                messages=[{"role": "user", "content": "Reply with exactly: cache_one"}],
            )
            _r2, resp2, _h2, _l2 = await client.messages_create(
                model=model,
                max_tokens=MAX_TOKENS,
                temperature=0,
                system=system_blocks,
                messages=[{"role": "user", "content": "Reply with exactly: cache_two"}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        u1 = resp1.get("usage") if isinstance(resp1.get("usage"), dict) else {}
        u2 = resp2.get("usage") if isinstance(resp2.get("usage"), dict) else {}

        c1_create = _int(u1.get("cache_creation_input_tokens"))
        c1_read = _int(u1.get("cache_read_input_tokens"))
        c1_input = _int(u1.get("input_tokens"))
        c2_create = _int(u2.get("cache_creation_input_tokens"))
        c2_read = _int(u2.get("cache_read_input_tokens"))
        c2_input = _int(u2.get("input_tokens"))

        has_cache_fields = any(
            k in u1 or k in u2
            for k in ("cache_creation_input_tokens", "cache_read_input_tokens")
        )
        call1_cached = (c1_create > 0) or (c1_read > 0)
        call2_hit = c2_read > 0

        score = 20.0 if (u1 and u2) else 0.0
        if call1_cached:
            score += 35.0
        elif has_cache_fields:
            score += 10.0
        if call2_hit:
            score += 45.0

        total_c2 = c2_input + c2_create + c2_read
        hit_ratio = round((c2_read / total_c2) * 100.0, 1) if total_c2 > 0 else 0.0

        details: dict[str, Any] = {
            "call1_input_tokens": c1_input,
            "call1_cache_creation": c1_create,
            "call1_cache_read": c1_read,
            "call2_input_tokens": c2_input,
            "call2_cache_creation": c2_create,
            "call2_cache_read": c2_read,
            "cache_hit_ratio_pct": hit_ratio,
            "cache_write_seen": c1_create > 0,
            "cache_read_hit": call2_hit,
            "sub_checks": {
                "cache_write": {"pass": call1_cached, "value": c1_create},
                "cache_read_hit": {"pass": call2_hit, "value": c2_read},
            },
        }
        status = "pass" if score >= 70.0 else "fail"
        return self._result(status, min(100.0, score), details)


def _int(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0

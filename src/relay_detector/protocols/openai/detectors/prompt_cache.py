"""OpenAI automatic Prompt Caching probe (1,024+ token prefix)."""

from __future__ import annotations

from typing import Any

from ....core.models import DetectorResult, Mode
from ....core.prompt_cache import build_cacheable_system_corpus
from .base import ActiveDetector


class PromptCacheDetector(ActiveDetector):
    name = "prompt_cache"
    display_name = "提示词缓存验证"
    weight = 8.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        corpus = build_cacheable_system_corpus()
        try:
            _r1, resp1, _h1, _l1 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=32,
                temperature=0,
                messages=[
                    {"role": "system", "content": corpus},
                    {"role": "user", "content": "Reply with exactly: cache_one"},
                ],
            )
            _r2, resp2, _h2, _l2 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=32,
                temperature=0,
                messages=[
                    {"role": "system", "content": corpus},
                    {"role": "user", "content": "Reply with exactly: cache_two"},
                ],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        u1 = resp1.get("usage") if isinstance(resp1.get("usage"), dict) else {}
        u2 = resp2.get("usage") if isinstance(resp2.get("usage"), dict) else {}
        d1 = u1.get("prompt_tokens_details") if isinstance(u1.get("prompt_tokens_details"), dict) else {}
        d2 = u2.get("prompt_tokens_details") if isinstance(u2.get("prompt_tokens_details"), dict) else {}

        c1_cached = _int(d1.get("cached_tokens"))
        c2_cached = _int(d2.get("cached_tokens"))
        c2_prompt = _int(u2.get("prompt_tokens"))
        has_details = bool(d1 or d2)

        hit = c2_cached > 0 or c1_cached > 0
        score = 20.0 if (u1 and u2) else 0.0
        if has_details:
            score += 25.0
        if hit:
            score += 55.0

        hit_ratio = round((max(c1_cached, c2_cached) / c2_prompt) * 100.0, 1) if c2_prompt > 0 else 0.0
        details: dict[str, Any] = {
            "call1_prompt_tokens": _int(u1.get("prompt_tokens")),
            "call1_cached_tokens": c1_cached,
            "call2_prompt_tokens": c2_prompt,
            "call2_cached_tokens": c2_cached,
            "cache_hit_ratio_pct": hit_ratio,
            "cache_read_hit": hit,
            "prompt_tokens_details_present": has_details,
            "sub_checks": {
                "details_field": {"pass": has_details},
                "cache_read_hit": {"pass": hit, "value": max(c1_cached, c2_cached)},
            },
        }
        status = "pass" if score >= 70.0 else "fail"
        return self._result(status, min(100.0, score), details)


def _int(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0

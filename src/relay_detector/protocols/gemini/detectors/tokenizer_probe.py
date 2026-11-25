"""Gemini tokenizer edge-case probe (SentencePiece BPE fidelity)."""

from __future__ import annotations

from typing import Any

from ....core.models import DetectorResult, Mode
from ....core.tokenizer_probe import (
    CONTROL_PROMPT,
    EDGE_PROBE_PROMPT,
    WHITESPACE_DIGIT_PROMPT,
    evaluate_tokenizer_probe,
)
from .base import ActiveDetector
from .utils import usage


class TokenizerProbeDetector(ActiveDetector):
    name = "tokenizer_probe"
    display_name = "分词器指纹检测"
    weight = 10.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        try:
            _r0, resp0, _h0, _l0 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=64,
                temperature=0,
                messages=[{"role": "user", "content": CONTROL_PROMPT}],
            )
            _r1, resp1, _h1, _l1 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=64,
                temperature=0,
                messages=[{"role": "user", "content": EDGE_PROBE_PROMPT}],
            )
            _r2, resp2, _h2, _l2 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=64,
                temperature=0,
                messages=[{"role": "user", "content": WHITESPACE_DIGIT_PROMPT}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        u0 = usage(resp0)
        u1 = usage(resp1)
        u2 = usage(resp2)
        fp = resp1.get("system_fingerprint") or resp0.get("system_fingerprint")
        ev = evaluate_tokenizer_probe(
            protocol="gemini",
            base_tokens=_int_or_none(u0.get("prompt_tokens")),
            edge_tokens=_int_or_none(u1.get("prompt_tokens")),
            ws_tokens=_int_or_none(u2.get("prompt_tokens")),
            edge_usage=u1,
            system_fingerprint=fp if isinstance(fp, str) else None,
        )
        score = float(ev.pop("score", 0.0))
        status = str(ev.pop("status", "fail"))
        return self._result(status, score, ev)


def _int_or_none(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None

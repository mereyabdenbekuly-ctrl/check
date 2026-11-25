"""Anthropic dynamic anti-cache reasoning challenge."""

from __future__ import annotations

from typing import Any

from ....core.dynamic_challenge import (
    evaluate_dynamic_challenge,
    generate_dynamic_challenge,
)
from ....core.models import DetectorResult, Mode
from .base import ActiveDetector


class DynamicChallengeDetector(ActiveDetector):
    name = "dynamic_challenge"
    display_name = "动态防缓存推理"
    weight = 6.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        challenge = generate_dynamic_challenge()
        try:
            _req, resp, _h, _lat = await client.messages_create(
                model=model,
                max_tokens=96,
                temperature=0,
                messages=[{"role": "user", "content": challenge["prompt"]}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        text = _join_text(resp.get("content"))
        ev = evaluate_dynamic_challenge(challenge, text)
        score = float(ev.pop("score", 0.0))
        status = str(ev.pop("status", "fail"))
        return self._result(status, score, ev)


def _join_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
    )

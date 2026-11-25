"""Gemini dynamic anti-cache reasoning challenge."""

from __future__ import annotations

from ....core.dynamic_challenge import (
    evaluate_dynamic_challenge,
    generate_dynamic_challenge,
)
from ....core.models import DetectorResult, Mode
from .base import ActiveDetector
from .utils import message_text


class DynamicChallengeDetector(ActiveDetector):
    name = "dynamic_challenge"
    display_name = "动态防缓存推理"
    weight = 6.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        challenge = generate_dynamic_challenge()
        try:
            _req, resp, _h, _lat = await client.chat_completions_create(
                model=model,
                max_completion_tokens=1024,
                temperature=0,
                messages=[{"role": "user", "content": challenge["prompt"]}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        ev = evaluate_dynamic_challenge(challenge, message_text(resp))
        score = float(ev.pop("score", 0.0))
        status = str(ev.pop("status", "fail"))
        return self._result(status, score, ev)

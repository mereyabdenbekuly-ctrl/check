"""OpenAI dynamic anti-cache reasoning challenge."""

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
            _req, resp, _h, _lat = await client.chat_completions_create(
                model=model,
                max_completion_tokens=512,
                temperature=0,
                messages=[{"role": "user", "content": challenge["prompt"]}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        text = _extract_text(resp)
        ev = evaluate_dynamic_challenge(challenge, text)
        score = float(ev.pop("score", 0.0))
        status = str(ev.pop("status", "fail"))
        return self._result(status, score, ev)


def _extract_text(resp: dict[str, Any]) -> str:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = msg.get("content") if isinstance(msg, dict) else ""
    return content if isinstance(content, str) else ""

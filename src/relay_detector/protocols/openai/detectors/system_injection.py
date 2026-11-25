"""OpenAI hidden system-prompt injection & override audit detector."""

from __future__ import annotations

from typing import Any

from ....core.models import DetectorResult, Mode
from ....core.system_injection import (
    BARE_USER_PROMPT,
    CANARY_USER_PROMPT,
    evaluate_system_injection,
    make_canary_prompts,
)
from .base import ActiveDetector


class SystemInjectionDetector(ActiveDetector):
    name = "system_injection"
    display_name = "隐藏系统提示词检测"
    weight = 6.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        canary_token, sys_prompt = make_canary_prompts()
        try:
            _r1, canary_resp, _h1, _l1 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=128,
                temperature=0,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": CANARY_USER_PROMPT},
                ],
            )
            _r2, bare_resp, _h2, _l2 = await client.chat_completions_create(
                model=model,
                max_completion_tokens=32,
                temperature=0,
                messages=[{"role": "user", "content": BARE_USER_PROMPT}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        canary_text = _extract_text(canary_resp)
        bare_usage = bare_resp.get("usage") if isinstance(bare_resp.get("usage"), dict) else {}
        bare_in = bare_usage.get("prompt_tokens")
        if not isinstance(bare_in, int) or isinstance(bare_in, bool):
            bare_in = None

        ev = evaluate_system_injection(
            canary_token=canary_token,
            canary_text=canary_text,
            bare_input_tokens=bare_in,
        )
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

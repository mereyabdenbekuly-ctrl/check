"""Anthropic hidden system-prompt injection & override audit detector."""

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
            _r1, canary_resp, _h1, _l1 = await client.messages_create(
                model=model,
                max_tokens=48,
                temperature=0,
                system=sys_prompt,
                messages=[{"role": "user", "content": CANARY_USER_PROMPT}],
            )
            _r2, bare_resp, _h2, _l2 = await client.messages_create(
                model=model,
                max_tokens=12,
                temperature=0,
                messages=[{"role": "user", "content": BARE_USER_PROMPT}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        canary_text = _join_text(canary_resp.get("content"))
        bare_usage = bare_resp.get("usage") if isinstance(bare_resp.get("usage"), dict) else {}
        bare_in = bare_usage.get("input_tokens")
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


def _join_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
    )

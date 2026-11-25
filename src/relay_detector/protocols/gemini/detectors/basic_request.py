"""Smallest possible Chat Completions probe — does the relay reply at all?"""

from __future__ import annotations

from ....core.models import DetectorResult
from .base import ActiveDetector
from .utils import finish_reason, message_text, usage


class BasicRequestDetector(ActiveDetector):
    name = "basic_request"
    display_name = "基础请求"
    weight = 15.0

    async def run(self, client, model: str) -> DetectorResult:
        try:
            # 512 tokens: Gemini 3/4 series default to thinking-on, with
            # reasoning tokens easily burning 64-256 tokens before emitting
            # "pong". Non-thinking models stop after 1 token anyway.
            _req, resp, _h, _lat = await client.chat_completions_create(
                model=model,
                max_completion_tokens=512,
                temperature=0,
                messages=[{"role": "user", "content": "Reply with exactly: pong"}],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        text = message_text(resp)
        ok = "pong" in text.lower()
        score = 100.0 if ok else 50.0 if text else 0.0
        return self._result(
            "pass" if score >= 70.0 else "fail",
            score,
            {
                "response_text": text[:300],
                "object": resp.get("object"),
                "model": resp.get("model"),
                "id": resp.get("id"),
                "finish_reason": finish_reason(resp),
                "usage": usage(resp),
            },
        )

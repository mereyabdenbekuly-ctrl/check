"""Anthropic dynamic PNG vision probe."""

from __future__ import annotations

from typing import Any

from ....core.models import DetectorResult, Mode
from ....core.vision_image import (
    VISION_PROMPT,
    evaluate_vision_response,
    generate_vision_challenge,
)
from .base import ActiveDetector


class VisionImageDetector(ActiveDetector):
    name = "vision_image"
    display_name = "图像视觉识别"
    weight = 7.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        expected_code, png_b64 = generate_vision_challenge()
        try:
            _req, resp, _h, _lat = await client.messages_create(
                model=model,
                max_tokens=48,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": png_b64,
                                },
                            },
                            {"type": "text", "text": VISION_PROMPT},
                        ],
                    }
                ],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        text = _join_text(resp.get("content"))
        ev = evaluate_vision_response(expected_code, text)
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

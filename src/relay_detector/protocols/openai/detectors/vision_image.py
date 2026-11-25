"""OpenAI dynamic PNG vision probe."""

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
            _req, resp, _h, _lat = await client.chat_completions_create(
                model=model,
                max_completion_tokens=512,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                            },
                        ],
                    }
                ],
            )
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        text = _extract_text(resp)
        ev = evaluate_vision_response(expected_code, text)
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

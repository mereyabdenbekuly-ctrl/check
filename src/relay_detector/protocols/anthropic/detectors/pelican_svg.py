"""Anthropic Pelican-on-a-bicycle SVG visual benchmark (streamed for real tok/s)."""

from __future__ import annotations

from ....core.models import DetectorResult, Mode
from ....core.pelican import PELICAN_PROMPT, extract_and_evaluate_pelican_svg
from .base import ActiveDetector


MAX_TOKENS = 3200


class PelicanSVGDetector(ActiveDetector):
    name = "pelican_svg"
    display_name = "鹈鹕骑车 SVG 测试"
    weight = 8.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        chunks: list[str] = []
        chunk_count = 0
        try:
            async for ev, _elapsed in client.messages_stream(
                model=model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": PELICAN_PROMPT}],
            ):
                if ev.event == "content_block_delta":
                    delta = ev.data.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        t = delta.get("text")
                        if isinstance(t, str) and t:
                            chunks.append(t)
                            chunk_count += 1
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        raw_text = "".join(chunks)
        ev_res = extract_and_evaluate_pelican_svg(raw_text)
        score = float(ev_res.pop("score", 0.0))
        status = str(ev_res.pop("status", "fail"))
        ev_res["stream_chunk_count"] = chunk_count
        return self._result(status, score, ev_res)

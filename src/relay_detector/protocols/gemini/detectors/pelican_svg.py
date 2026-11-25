"""Gemini Pelican-on-a-bicycle SVG visual benchmark (streamed for real tok/s)."""

from __future__ import annotations

from ....core.models import DetectorResult, Mode
from ....core.pelican import PELICAN_PROMPT, extract_and_evaluate_pelican_svg
from .base import ActiveDetector


MAX_COMPLETION_TOKENS = 4096


class PelicanSVGDetector(ActiveDetector):
    name = "pelican_svg"
    display_name = "鹈鹕骑车 SVG 测试"
    weight = 8.0
    modes = {Mode.FULL}

    async def run(self, client, model: str) -> DetectorResult:
        chunks: list[str] = []
        chunk_count = 0
        body = {
            "model": model,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "messages": [{"role": "user", "content": PELICAN_PROMPT}],
            "stream_options": {"include_usage": True},
        }
        try:
            try:
                async for chunk, _elapsed in client.chat_completions_stream(**body):
                    for choice in chunk.get("choices") or []:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            chunks.append(content)
                            chunk_count += 1
            except Exception:
                body.pop("stream_options", None)
                chunks.clear()
                chunk_count = 0
                async for chunk, _elapsed in client.chat_completions_stream(**body):
                    for choice in chunk.get("choices") or []:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            chunks.append(content)
                            chunk_count += 1
        except Exception as e:  # noqa: BLE001
            return self._result("error", 0.0, error=str(e))

        ev_res = extract_and_evaluate_pelican_svg("".join(chunks))
        score = float(ev_res.pop("score", 0.0))
        status = str(ev_res.pop("status", "fail"))
        ev_res["stream_chunk_count"] = chunk_count
        return self._result(status, score, ev_res)

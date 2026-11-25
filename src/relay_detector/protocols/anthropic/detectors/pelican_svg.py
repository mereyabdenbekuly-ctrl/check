"""Anthropic Pelican-on-a-bicycle SVG visual benchmark (streamed for real tok/s)."""

from __future__ import annotations

from ....core.models import DetectorResult, Mode
from ....core.pelican import PELICAN_PROMPT, extract_and_evaluate_pelican_svg
from ..config import lookup_model
from .base import ActiveDetector


MAX_TOKENS = 16384
_VALID_EFFORTS = frozenset({"low", "medium", "high"})


class PelicanSVGDetector(ActiveDetector):
    name = "pelican_svg"
    display_name = "鹈鹕骑车 SVG 测试"
    weight = 8.0
    modes = {Mode.FULL}

    def __init__(self, reasoning_effort: str | None = None) -> None:
        super().__init__()
        self.reasoning_effort = reasoning_effort

    async def run(self, client, model: str) -> DetectorResult:
        chunks: list[str] = []
        chunk_count = 0
        req_effort = (self.reasoning_effort or "").strip().lower()
        use_effort = req_effort if req_effort in _VALID_EFFORTS else None

        base_kwargs: dict = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": PELICAN_PROMPT}],
        }
        attempts: list[tuple[str | None, dict]] = []
        if use_effort:
            info = lookup_model(model)
            if info is None or info.supports_adaptive_thinking:
                kw = dict(base_kwargs)
                kw["thinking"] = {"type": "adaptive"}
                kw["output_config"] = {"effort": use_effort}
                attempts.append((use_effort, kw))
        attempts.append((None, base_kwargs))

        effective_effort: str | None = None
        last_err: Exception | None = None
        for eff, kw in attempts:
            chunks.clear()
            chunk_count = 0
            try:
                async for ev, _elapsed in client.messages_stream(**kw):
                    if ev.event == "content_block_delta":
                        delta = ev.data.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            t = delta.get("text")
                            if isinstance(t, str) and t:
                                chunks.append(t)
                                chunk_count += 1
                effective_effort = eff
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue

        if last_err is not None:
            return self._result("error", 0.0, error=str(last_err))

        raw_text = "".join(chunks)
        ev_res = extract_and_evaluate_pelican_svg(raw_text)
        score = float(ev_res.pop("score", 0.0))
        status = str(ev_res.pop("status", "fail"))
        ev_res["stream_chunk_count"] = chunk_count
        ev_res["reasoning_effort"] = effective_effort or "default"
        return self._result(status, score, ev_res)

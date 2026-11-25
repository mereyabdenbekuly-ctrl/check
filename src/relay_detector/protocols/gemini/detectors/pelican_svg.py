"""Gemini Pelican-on-a-bicycle SVG visual benchmark (streamed for real tok/s)."""

from __future__ import annotations

from ....core.models import DetectorResult, Mode
from ....core.pelican import PELICAN_PROMPT, extract_and_evaluate_pelican_svg
from .base import ActiveDetector


_VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


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
        effort = req_effort if req_effort in _VALID_EFFORTS else None

        # Omit max_completion_tokens so Gemini uses its full native output
        # window for both thinking tokens and detailed SVG markup.
        base_body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": PELICAN_PROMPT}],
            "stream_options": {"include_usage": True},
        }
        if effort:
            base_body["reasoning_effort"] = effort

        attempts: list[dict] = [dict(base_body)]
        if "stream_options" in base_body:
            no_so = dict(base_body)
            no_so.pop("stream_options", None)
            attempts.append(no_so)
        if effort in ("xhigh", "max"):
            downgraded = dict(base_body)
            downgraded["reasoning_effort"] = "high"
            attempts.append(downgraded)
        if "reasoning_effort" in base_body:
            no_re = dict(base_body)
            no_re.pop("reasoning_effort", None)
            no_re.pop("stream_options", None)
            attempts.append(no_re)

        effective_effort = effort
        last_err: Exception | None = None
        for body in attempts:
            chunks.clear()
            chunk_count = 0
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
                effective_effort = body.get("reasoning_effort")
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue

        if last_err is not None:
            return self._result("error", 0.0, error=str(last_err))

        ev_res = extract_and_evaluate_pelican_svg("".join(chunks))
        score = float(ev_res.pop("score", 0.0))
        status = str(ev_res.pop("status", "fail"))
        ev_res["stream_chunk_count"] = chunk_count
        ev_res["reasoning_effort"] = effective_effort or "default"
        return self._result(status, score, ev_res)

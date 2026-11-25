"""OpenAI Pelican-on-a-bicycle SVG visual benchmark (streamed for real tok/s)."""

from __future__ import annotations

from ....core.models import DetectorResult, Mode
from ....core.pelican import PELICAN_PROMPT, extract_and_evaluate_pelican_svg
from .base import ActiveDetector


MAX_COMPLETION_TOKENS = 16384
_VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
_EXPLICIT_MODEL_EFFORT_SUFFIXES = ("-low", "-medium", "-high", "-xhigh", "-max", "-ultra")


def _supports_openai_reasoning(model: str) -> bool:
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.rsplit("/", 1)[-1]
    if m.startswith(("gpt-4", "gpt-3", "chatgpt", "gpt-5-chat")):
        return False
    return m.startswith(("gpt-6", "gpt-5", "o1", "o3", "o4", "codex-"))


def _resolve_openai_effort(model: str, requested: str | None) -> str | None:
    req = (requested or "").strip().lower()
    if req in ("none", "off", "default"):
        return None
    if req in _VALID_EFFORTS:
        return req
    # Auto mode: let an explicit model-name suffix (-high, -low, etc.) win;
    # otherwise enable high reasoning on GPT-5/GPT-6/o-series so spatial SVG
    # geometry is planned deeply instead of falling back to minimal/low.
    m = (model or "").strip().lower()
    if m.endswith(_EXPLICIT_MODEL_EFFORT_SUFFIXES):
        return None
    return "high" if _supports_openai_reasoning(m) else None


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
        effort = _resolve_openai_effort(model, self.reasoning_effort)
        base_body: dict = {
            "model": model,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
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

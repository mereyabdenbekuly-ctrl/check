"""Tests for Pelican SVG, Prompt Caching, System Injection, Tokenizer Probe, and Stream Analysis."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from relay_detector.core.pelican import extract_and_evaluate_pelican_svg
from relay_detector.core.prompt_cache import build_cacheable_system_corpus
from relay_detector.core.stream_metrics import StreamSample, summarize_stream_samples
from relay_detector.core.system_injection import evaluate_system_injection, make_canary_prompts
from relay_detector.core.tokenizer_probe import evaluate_tokenizer_probe
from relay_detector.protocols.anthropic.detectors.prompt_cache import (
    PromptCacheDetector as AnthropicPromptCacheDetector,
)
from relay_detector.protocols.openai.detectors.prompt_cache import (
    PromptCacheDetector as OpenAIPromptCacheDetector,
)
from web import jobs
from web.image_report import render_report_jpg
from web.server import app


RICH_PELICAN_SVG = """```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" onload="alert(1)">
  <script>alert('xss')</script>
  <foreignObject><div>evil</div></foreignObject>
  <rect x="0" y="0" width="400" height="300" fill="#e0f2fe" />
  <circle cx="120" cy="220" r="45" fill="none" stroke="#1e293b" stroke-width="5" onclick="evil()" />
  <circle cx="280" cy="220" r="45" fill="none" stroke="#1e293b" stroke-width="5" />
  <circle cx="120" cy="220" r="6" fill="#64748b" />
  <circle cx="280" cy="220" r="6" fill="#64748b" />
  <line x1="120" y1="220" x2="195" y2="220" stroke="#ef4444" stroke-width="4" />
  <line x1="195" y1="220" x2="255" y2="155" stroke="#ef4444" stroke-width="4" />
  <line x1="120" y1="220" x2="175" y2="150" stroke="#ef4444" stroke-width="4" />
  <line x1="175" y1="150" x2="255" y2="155" stroke="#ef4444" stroke-width="4" />
  <line x1="255" y1="155" x2="280" y2="220" stroke="#ef4444" stroke-width="4" />
  <line x1="255" y1="155" x2="265" y2="125" stroke="#334155" stroke-width="4" />
  <path d="M250 125 Q275 120 285 130" fill="none" stroke="#334155" stroke-width="4" />
  <rect x="158" y="142" width="32" height="8" rx="4" fill="#0f172a" />
  <ellipse cx="185" cy="122" rx="34" ry="22" fill="#ffffff" stroke="#475569" stroke-width="2" />
  <path d="M160 118 Q185 100 212 124 Q190 138 160 118 Z" fill="#e2e8f0" />
  <path d="M210 110 Q222 86 232 78" fill="none" stroke="#ffffff" stroke-width="14" stroke-linecap="round" />
  <circle cx="235" cy="74" r="14" fill="#ffffff" stroke="#475569" stroke-width="2" />
  <circle cx="240" cy="71" r="2.5" fill="#0f172a" />
  <path d="M246 72 L300 78 L246 84 Z" fill="#f59e0b" />
  <path d="M248 80 Q276 105 296 80 Z" fill="#fbbf24" stroke="#d97706" stroke-width="1.5" />
  <line x1="185" y1="144" x2="195" y2="215" stroke="#f97316" stroke-width="3" />
</svg>
```"""


def test_pelican_svg_sanitizes_xss_and_scores_frontier_svg():
    res = extract_and_evaluate_pelican_svg(RICH_PELICAN_SVG)
    assert res["valid_svg"] is True
    assert res["status"] == "pass"
    assert res["score"] >= 95.0
    assert res["primitive_count"] >= 18
    assert res["unique_colors"] >= 5
    assert res["has_wheels"] is True
    svg = res["svg_sanitized"]
    assert "<script" not in svg.lower()
    assert "foreignobject" not in svg.lower()
    assert "onload" not in svg.lower()
    assert "onclick" not in svg.lower()
    assert svg.startswith("<svg") and svg.endswith("</svg>")


def test_pelican_svg_preserves_local_use_wheels_and_blocks_external_use():
    svg_with_use = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 400 300">
      <defs>
        <g id="wheel">
          <circle r="40" fill="none" stroke="#233047" stroke-width="8" />
          <path d="M-35 0h70M0-35v70" stroke="#627e8a" stroke-width="2" />
        </g>
      </defs>
      <rect width="400" height="300" fill="#86dce9" />
      <use href="#wheel" x="106" y="221" />
      <use xlink:href="#wheel" x="287" y="221" />
      <use href="https://evil.example/payload.svg#xss" x="0" y="0" />
      <use href="javascript:alert(1)" x="0" y="0" />
      <path d="M106 221 L156 169 L251 165 L287 221" fill="none" stroke="#14aa9f" stroke-width="6" />
      <ellipse cx="185" cy="122" rx="34" ry="22" fill="#fff9e7" stroke="#233047" stroke-width="3" />
      <path d="M246 72 L300 78 L246 84 Z" fill="#ffbe49" />
    </svg>"""
    res = extract_and_evaluate_pelican_svg(svg_with_use)
    assert res["valid_svg"] is True
    out = res["svg_sanitized"]
    assert '<use href="#wheel" x="106" y="221"' in out
    assert '<use href="#wheel" x="287" y="221"' in out
    assert "evil.example" not in out
    assert "javascript:" not in out


def test_pelican_svg_rejects_dtd_and_fails_crude_shapes():
    evil = '<!DOCTYPE svg [<!ENTITY xxe "boom">]><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="10"/></svg>'
    assert extract_and_evaluate_pelican_svg(evil)["valid_svg"] is False

    crude = '<svg viewBox="0 0 100 100"><circle cx="20" cy="20" r="10"/><line x1="0" y1="0" x2="10" y2="10"/></svg>'
    res = extract_and_evaluate_pelican_svg(crude)
    assert res["valid_svg"] is True
    assert res["status"] == "fail"
    assert res["score"] < 70.0


def test_system_injection_canary_and_overhead():
    token, sys_prompt = make_canary_prompts()
    assert token in sys_prompt

    clean = evaluate_system_injection(
        canary_token=token,
        canary_text=f"[{token}] 4",
        bare_input_tokens=19,
    )
    assert clean["status"] == "pass"
    assert clean["score"] == 100.0

    bloated = evaluate_system_injection(
        canary_token=token,
        canary_text=f"[{token}] 4",
        bare_input_tokens=420,
    )
    assert bloated["status"] == "fail"
    assert bloated["overhead_label"] == "heavy_injection"

    overridden = evaluate_system_injection(
        canary_token=token,
        canary_text="The answer is 4.",
        bare_input_tokens=15,
    )
    assert overridden["status"] == "fail"
    assert overridden["canary_followed"] is False


def test_tokenizer_probe_openai_and_gemini():
    ok_openai = evaluate_tokenizer_probe(
        protocol="openai",
        base_tokens=11,
        edge_tokens=138,
        ws_tokens=68,
        edge_usage={"prompt_tokens": 138, "completion_tokens": 2, "total_tokens": 140},
        system_fingerprint="fp_abc123",
    )
    assert ok_openai["status"] == "pass"
    assert ok_openai["score"] == 100.0

    bad_proxy = evaluate_tokenizer_probe(
        protocol="openai",
        base_tokens=11,
        edge_tokens=480,
        ws_tokens=360,
        edge_usage={"prompt_tokens": 480, "completion_tokens": 2, "total_tokens": 482},
    )
    assert bad_proxy["status"] == "fail"

    ok_gemini = evaluate_tokenizer_probe(
        protocol="gemini",
        base_tokens=10,
        edge_tokens=155,
        ws_tokens=82,
        edge_usage={"prompt_tokens": 155, "completion_tokens": 4, "total_tokens": 175},
    )
    assert ok_gemini["status"] == "pass"


def test_stream_sample_distinguishes_real_stream_vs_buffered_burst():
    real = StreamSample()
    for i in range(20):
        real.record_delta(300 + i * 50, "word ")
    real.output_tokens = 50
    real_fin = real.finalize()
    assert real_fin is not None
    assert real_fin["verdict"] == "real_stream"
    assert real_fin["tokens_per_second"] == pytest.approx(52.6, rel=0.05)

    burst = StreamSample()
    burst.record_delta(2400, "A" * 240)
    burst.output_tokens = 60
    burst_fin = burst.finalize()
    assert burst_fin is not None
    assert burst_fin["verdict"] == "buffered_burst"

    tps, analysis = summarize_stream_samples([real_fin])
    assert tps == real_fin["tokens_per_second"]
    assert analysis["verdict"] == "real_stream"

    _, burst_analysis = summarize_stream_samples([burst_fin])
    assert burst_analysis["verdict"] == "buffered_burst"


@pytest.mark.asyncio
async def test_prompt_cache_detectors_anthropic_and_openai():
    corpus = build_cacheable_system_corpus("deadbeef")
    assert len(corpus) > 8000

    class FakeAnthropicCacheClient:
        def __init__(self):
            self.calls = 0

        async def messages_create(self, **body):
            self.calls += 1
            if self.calls == 1:
                usage = {"input_tokens": 12, "cache_creation_input_tokens": 2250, "cache_read_input_tokens": 0, "output_tokens": 2}
            else:
                usage = {"input_tokens": 12, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 2250, "output_tokens": 2}
            return body, {"usage": usage, "content": [{"type": "text", "text": "ok"}]}, httpx.Headers(), 50

    res_a = await AnthropicPromptCacheDetector().run(FakeAnthropicCacheClient(), "claude-sonnet-5-5")
    assert res_a.status == "pass"
    assert res_a.score == 100.0
    assert res_a.details["cache_read_hit"] is True

    class FakeOpenAICacheClient:
        def __init__(self):
            self.calls = 0

        async def chat_completions_create(self, **body):
            self.calls += 1
            cached = 0 if self.calls == 1 else 2048
            usage = {
                "prompt_tokens": 2200,
                "completion_tokens": 2,
                "total_tokens": 2202,
                "prompt_tokens_details": {"cached_tokens": cached},
            }
            return body, {"usage": usage, "choices": [{"message": {"content": "ok"}}]}, httpx.Headers(), 50

    res_o = await OpenAIPromptCacheDetector().run(FakeOpenAICacheClient(), "gpt-6.2-sol")
    assert res_o.status == "pass"
    assert res_o.score == 100.0
    assert res_o.details["cache_read_hit"] is True


def test_result_page_pelican_showcase_svg_download_and_jpg_rendering():
    pelican_eval = extract_and_evaluate_pelican_svg(RICH_PELICAN_SVG)
    job_id = "testpel1"
    report = {
        "protocol": "anthropic",
        "base_url": "https://clodex.xyz",
        "target_model": "claude-sonnet-5-5",
        "mode": "full",
        "total_score": 96.0,
        "verdict": "passed",
        "results": [
            {"name": "thinking_signature", "status": "pass", "score": 100.0},
            {"name": "prompt_cache", "status": "pass", "score": 100.0, "details": {"call2_cache_read": 2200, "cache_hit_ratio_pct": 99.1}},
            {"name": "system_injection", "status": "pass", "score": 100.0, "details": {"canary_followed": True, "bare_input_tokens": 21}},
            {"name": "pelican_svg", "status": "pass", "score": pelican_eval["score"], "details": pelican_eval},
        ],
        "performance": {
            "ttft_ms": 420,
            "total_latency_ms": 14200,
            "tokens_per_second": 74.5,
            "stream_analysis": {"verdict": "real_stream", "chunk_count": 64, "median_gap_ms": 18.0},
            "usage": {"input_tokens": 4100, "output_tokens": 920},
        },
    }
    jobs._JOBS[job_id] = jobs.Job(
        id=job_id,
        protocol="anthropic",
        status="done",
        base_url="https://clodex.xyz",
        target_model="claude-sonnet-5-5",
        mode="full",
        report=report,
    )
    try:
        client = TestClient(app)
        page = client.get(f"/r/{job_id}")
        assert page.status_code == 200
        assert "data:image/svg+xml;base64," in page.text
        assert "74.5" in page.text
        assert "Реальный стрим" in page.text
        assert "Prompt Caching работает реально" in page.text

        svg_dl = client.get(f"/r/{job_id}/pelican.svg")
        assert svg_dl.status_code == 200
        assert svg_dl.headers["content-type"].startswith("image/svg+xml")
        assert svg_dl.headers["content-security-policy"] == "sandbox"
        assert "<script" not in svg_dl.text.lower()
        assert svg_dl.text.startswith("<svg")

        jpg_bytes = render_report_jpg(report, locale="ru")
        assert jpg_bytes[:3] == b"\xff\xd8\xff"
        assert len(jpg_bytes) > 15_000
    finally:
        jobs._JOBS.pop(job_id, None)


@pytest.mark.asyncio
async def test_openai_pelican_auto_reasoning_effort_and_fallback():
    from relay_detector.protocols.openai.detectors.pelican_svg import (
        PelicanSVGDetector as OpenAIPelican,
        _resolve_openai_effort,
    )
    from relay_detector.protocols.anthropic.detectors.pelican_svg import (
        _anthropic_max_tokens,
    )

    assert _anthropic_max_tokens("claude-opus-5-5") == 128_000
    assert _anthropic_max_tokens("claude-sonnet-5-5") == 64_000

    assert _resolve_openai_effort("gpt-6.2-sol", None) == "high"
    assert _resolve_openai_effort("gpt-6.2-sol", "auto") == "high"
    assert _resolve_openai_effort("gpt-6.2-sol", "xhigh") == "xhigh"
    assert _resolve_openai_effort("gpt-6.2-sol", "max") == "max"
    assert _resolve_openai_effort("gpt-6.2-sol", "medium") == "medium"
    assert _resolve_openai_effort("gpt-6.2-sol", "none") is None
    assert _resolve_openai_effort("gpt-6.2-sol-low", "auto") is None
    assert _resolve_openai_effort("gpt-4o", "auto") is None

    seen_bodies: list[dict] = []

    class _FakeClient:
        async def chat_completions_stream(self, **kwargs):
            seen_bodies.append(dict(kwargs))
            # Reject reasoning_effort on first two attempts to test graceful fallback.
            if "reasoning_effort" in kwargs:
                raise RuntimeError("unsupported parameter: reasoning_effort")
            yield {"choices": [{"delta": {"content": RICH_PELICAN_SVG}}]}, 10.0

    res = await OpenAIPelican(reasoning_effort="auto").run(_FakeClient(), "gpt-6.2-sol")
    assert res.status == "pass"
    assert seen_bodies[0].get("reasoning_effort") == "high"
    assert "max_completion_tokens" not in seen_bodies[0]
    assert "reasoning_effort" not in seen_bodies[-1]
    assert res.details["reasoning_effort"] == "default"


def test_pelican_page_exposes_reasoning_effort_selector():
    client = TestClient(app)
    for path in ("/pelican", "/openai", "/claude", "/gemini"):
        r = client.get(path)
        assert r.status_code == 200
        assert 'id="pelican_reasoning_effort"' in r.text
        assert 'value="xhigh"' in r.text
    for path in ("/pelican", "/openai", "/claude"):
        r = client.get(path)
        assert 'value="max"' in r.text

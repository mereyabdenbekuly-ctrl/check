"""Tests for v4 flagship features: dynamic PNG vision, anti-cache challenge, /compare, and 17-row JPG."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from relay_detector.core.dynamic_challenge import (
    evaluate_dynamic_challenge,
    generate_dynamic_challenge,
)
from relay_detector.core.models import Mode
from relay_detector.core.pelican import extract_and_evaluate_pelican_svg
from relay_detector.core.vision_image import (
    evaluate_vision_response,
    generate_vision_challenge,
)
from relay_detector.protocols.anthropic import build_detectors as build_anthropic_detectors
from relay_detector.protocols.anthropic.detectors.dynamic_challenge import (
    DynamicChallengeDetector as AnthropicDynamicDetector,
)
from relay_detector.protocols.anthropic.detectors.vision_image import (
    VisionImageDetector as AnthropicVisionDetector,
)
from relay_detector.protocols.gemini import build_detectors as build_gemini_detectors
from relay_detector.protocols.gemini.detectors.dynamic_challenge import (
    DynamicChallengeDetector as GeminiDynamicDetector,
)
from relay_detector.protocols.gemini.detectors.vision_image import (
    VisionImageDetector as GeminiVisionDetector,
)
from relay_detector.protocols.openai import build_detectors as build_openai_detectors
from relay_detector.protocols.openai.detectors.dynamic_challenge import (
    DynamicChallengeDetector as OpenAIDynamicDetector,
)
from relay_detector.protocols.openai.detectors.vision_image import (
    VisionImageDetector as OpenAIVisionDetector,
)
from tests.test_v3_detectors import RICH_PELICAN_SVG
from web import jobs
from web.image_report import render_report_jpg
from web.server import _extract_job_id, app


def test_detector_registry_counts_across_all_protocols():
    from relay_detector.protocols.anthropic.config import MODE_DETECTORS as ANTHROPIC_MODES
    from relay_detector.protocols.gemini.config import MODE_DETECTORS as GEMINI_MODES
    from relay_detector.protocols.openai.config import MODE_DETECTORS as OPENAI_MODES

    assert len(build_anthropic_detectors(Mode.FULL)) == 17
    assert len(build_openai_detectors(Mode.FULL)) == 14
    assert len(build_gemini_detectors(Mode.FULL)) == 12
    assert len(ANTHROPIC_MODES[Mode.FULL]) == 17
    assert len(OPENAI_MODES[Mode.FULL]) == 14
    assert len(GEMINI_MODES[Mode.FULL]) == 12
    # Standard mode stays backwards-compatible
    assert "vision_image" not in OPENAI_MODES[Mode.STANDARD]
    assert "dynamic_challenge" not in GEMINI_MODES[Mode.STANDARD]


def test_vision_image_png_generation_and_evaluation():
    code, b64 = generate_vision_challenge()
    assert code.startswith("VRF-")
    assert len(code) == 8
    raw = base64.b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 800

    exact = evaluate_vision_response(code, f"  {code}  ")
    assert exact["status"] == "pass"
    assert exact["score"] == 100.0
    assert exact["verdict"] == "exact_match"

    digits = evaluate_vision_response(code, f"The digits are {code.split('-')[1]}")
    assert digits["status"] == "pass"
    assert digits["score"] == 80.0
    assert digits["verdict"] == "digits_matched"

    missed = evaluate_vision_response(code, "I cannot see images.")
    assert missed["status"] == "fail"
    assert missed["score"] == 0.0
    assert missed["verdict"] == "vision_failed"


def test_dynamic_challenge_generation_and_evaluation():
    ch = generate_dynamic_challenge()
    assert ch["expected_calc"] == ch["a"] * ch["b"] + ch["c"]
    assert ch["expected_rev"] == ch["word"][::-1]

    perfect = evaluate_dynamic_challenge(
        ch,
        json.dumps({"calc": ch["expected_calc"], "rev": ch["expected_rev"]}),
    )
    assert perfect["status"] == "pass"
    assert perfect["score"] == 100.0

    lenient = evaluate_dynamic_challenge(
        ch,
        f"Result is {ch['expected_calc']} and reversed is {ch['expected_rev']}",
    )
    assert lenient["status"] == "pass"
    assert lenient["score"] == 80.0

    wrong = evaluate_dynamic_challenge(
        ch,
        json.dumps({"calc": ch["expected_calc"] + 1, "rev": "wrong"}),
    )
    assert wrong["status"] == "fail"
    assert wrong["score"] == 20.0


@pytest.mark.asyncio
async def test_vision_and_dynamic_detectors_across_all_three_protocols(monkeypatch):
    monkeypatch.setattr(
        "relay_detector.protocols.anthropic.detectors.vision_image.generate_vision_challenge",
        lambda: ("VRF-7392", "iVBORw0KGgo="),
    )
    monkeypatch.setattr(
        "relay_detector.protocols.openai.detectors.vision_image.generate_vision_challenge",
        lambda: ("VRF-7392", "iVBORw0KGgo="),
    )
    monkeypatch.setattr(
        "relay_detector.protocols.gemini.detectors.vision_image.generate_vision_challenge",
        lambda: ("VRF-7392", "iVBORw0KGgo="),
    )

    fixed_ch = {
        "a": 15,
        "b": 12,
        "c": 9,
        "word": "pelican42",
        "expected_calc": 189,
        "expected_rev": "24nacilep",
        "prompt": "Compute 15 * 12 + 9 and reverse pelican42",
    }
    for mod in (
        "relay_detector.protocols.anthropic.detectors.dynamic_challenge",
        "relay_detector.protocols.openai.detectors.dynamic_challenge",
        "relay_detector.protocols.gemini.detectors.dynamic_challenge",
    ):
        monkeypatch.setattr(f"{mod}.generate_dynamic_challenge", lambda: fixed_ch)

    class FakeAnthropic:
        async def messages_create(self, **body):
            content = body["messages"][0]["content"]
            if isinstance(content, list):
                txt = "VRF-7392"
            else:
                txt = '{"calc": 189, "rev": "24nacilep"}'
            return body, {"content": [{"type": "text", "text": txt}]}, httpx.Headers(), 40

    class FakeChat:
        async def chat_completions_create(self, **body):
            content = body["messages"][0]["content"]
            if isinstance(content, list):
                txt = "VRF-7392"
            else:
                txt = '{"calc": 189, "rev": "24nacilep"}'
            return body, {"choices": [{"message": {"content": txt}}]}, httpx.Headers(), 40

    for det, cli in [
        (AnthropicVisionDetector(), FakeAnthropic()),
        (OpenAIVisionDetector(), FakeChat()),
        (GeminiVisionDetector(), FakeChat()),
        (AnthropicDynamicDetector(), FakeAnthropic()),
        (OpenAIDynamicDetector(), FakeChat()),
        (GeminiDynamicDetector(), FakeChat()),
    ]:
        res = await det.run(cli, "test-model")
        assert res.status == "pass"
        assert res.score == 100.0


def test_extract_job_id_handles_urls_and_rejects_traversal():
    assert _extract_job_id("4VFI4sNK") == "4VFI4sNK"
    assert _extract_job_id("https://check.clodex.xyz/r/4VFI4sNK?lang=en") == "4VFI4sNK"
    assert _extract_job_id("https://check.clodex.xyz/r/4VFI4sNK.jpg") == "4VFI4sNK"
    assert _extract_job_id("https://check.clodex.xyz/r/4VFI4sNK/pelican.svg") == "4VFI4sNK"
    assert _extract_job_id("../../etc/passwd") == ""


def test_compare_page_empty_error_and_side_by_side_diff_with_pelicans():
    pelican_eval = extract_and_evaluate_pelican_svg(RICH_PELICAN_SVG)
    id_a, id_b = "cmpA1234", "cmpB5678"

    report_a = {
        "protocol": "anthropic",
        "base_url": "https://relay-a.example",
        "target_model": "claude-sonnet-5-5",
        "mode": "full",
        "total_score": 72.0,
        "verdict": "marginal",
        "results": [
            {"name": "thinking_signature", "status": "fail", "score": 0.0, "details": {"evaluation": "missing"}},
            {"name": "prompt_cache", "status": "fail", "score": 0.0, "details": {"cache_read_hit": False}},
            {"name": "vision_image", "status": "pass", "score": 100.0, "details": {"verdict": "exact_match", "expected_code": "VRF-2345"}},
            {"name": "dynamic_challenge", "status": "pass", "score": 100.0, "details": {"calc_ok": True, "rev_ok": True}},
            {"name": "pelican_svg", "status": "fail", "score": 45.0, "details": {"valid_svg": False, "reason": "no svg"}},
        ],
        "performance": {
            "ttft_ms": 1450,
            "total_latency_ms": 21000,
            "tokens_per_second": 32.4,
            "stream_analysis": {"verdict": "buffered_burst", "chunk_count": 2},
            "usage": {"input_tokens": 3500, "output_tokens": 600},
        },
    }
    report_b = {
        "protocol": "anthropic",
        "base_url": "https://clodex.xyz",
        "target_model": "claude-sonnet-5-5",
        "mode": "full",
        "total_score": 100.0,
        "verdict": "passed",
        "results": [
            {"name": "thinking_signature", "status": "pass", "score": 100.0, "details": {"signature_length": 912}},
            {"name": "prompt_cache", "status": "pass", "score": 100.0, "details": {"cache_read_hit": True, "call2_cache_read": 2250, "cache_hit_ratio_pct": 99.1}},
            {"name": "vision_image", "status": "pass", "score": 100.0, "details": {"verdict": "exact_match", "expected_code": "VRF-8765"}},
            {"name": "dynamic_challenge", "status": "pass", "score": 100.0, "details": {"calc_ok": True, "rev_ok": True}},
            {"name": "pelican_svg", "status": "pass", "score": pelican_eval["score"], "details": pelican_eval},
        ],
        "performance": {
            "ttft_ms": 380,
            "total_latency_ms": 12400,
            "tokens_per_second": 84.2,
            "stream_analysis": {"verdict": "real_stream", "chunk_count": 78},
            "usage": {"input_tokens": 3600, "output_tokens": 940},
        },
    }

    jobs._JOBS[id_a] = jobs.Job(id=id_a, protocol="anthropic", status="done", base_url=report_a["base_url"], target_model=report_a["target_model"], mode="full", report=report_a)
    jobs._JOBS[id_b] = jobs.Job(id=id_b, protocol="anthropic", status="done", base_url=report_b["base_url"], target_model=report_b["target_model"], mode="full", report=report_b)
    try:
        client = TestClient(app)

        empty = client.get("/compare")
        assert empty.status_code == 200
        assert "Сравнение двух отчётов" in empty.text

        missing = client.get("/compare?a=nonexistent999&b=cmpB5678")
        assert missing.status_code == 200
        assert "не найден" in missing.text

        # Pass full URL for A and bare ID for B
        res = client.get(f"/compare?a=https://check.clodex.xyz/r/{id_a}&b={id_b}")
        assert res.status_code == 200
        assert "relay-a.example" in res.text
        assert "clodex.xyz" in res.text
        assert "+28.0" in res.text
        assert "signature 912 B" in res.text
        assert "data:image/svg+xml;base64," in res.text
        assert "84.2" in res.text
    finally:
        jobs._JOBS.pop(id_a, None)
        jobs._JOBS.pop(id_b, None)


def test_jpg_renders_cleanly_with_all_17_anthropic_detectors():
    all_names = [d.name for d in build_anthropic_detectors(Mode.FULL)]
    assert len(all_names) == 17
    report = {
        "protocol": "anthropic",
        "base_url": "https://clodex.xyz",
        "target_model": "claude-opus-5-5",
        "mode": "full",
        "total_score": 100.0,
        "verdict": "passed",
        "results": [{"name": n, "status": "pass", "score": 100.0} for n in all_names],
        "performance": {
            "ttft_ms": 410,
            "total_latency_ms": 15200,
            "tokens_per_second": 79.3,
            "usage": {"input_tokens": 5200, "output_tokens": 1100},
        },
    }
    jpg = render_report_jpg(report, locale="ru")
    assert jpg[:3] == b"\xff\xd8\xff"
    assert len(jpg) > 20_000

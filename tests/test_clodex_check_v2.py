"""Regression tests for CLODEX Check v2 updates: models, SEO meta, UI routes, JPG rendering."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from relay_detector.protocols.anthropic.client import _sanitize_body as sanitize_anthropic_body
from relay_detector.protocols.anthropic.config import lookup_model
from relay_detector.protocols.anthropic.detectors.thinking_signature import ThinkingSignatureDetector
from web.image_report import render_report_jpg
from web.probe import _classify
from web.server import _seo_meta_for_report, app


def _sample_report(**overrides) -> dict:
    base = {
        "protocol": "anthropic",
        "base_url": "https://clodex.xyz",
        "target_model": "claude-opus-5-5",
        "mode": "full",
        "total_score": 98.0,
        "verdict": "passed",
        "results": [
            {"name": "thinking_signature", "status": "pass", "score": 100.0},
            {"name": "protocol", "status": "pass", "score": 100.0},
        ],
        "performance": {
            "ttft_ms": 420,
            "total_latency_ms": 8400,
            "usage": {"input_tokens": 1200, "output_tokens": 350},
        },
    }
    base.update(overrides)
    return base


def test_claude_5_series_lookup_and_thinking_support():
    for model_id in (
        "claude-opus-5-5",
        "claude-opus-5.5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-sonnet-5.5",
        "claude-haiku-5-5",
        "claude-fable-5-2",
    ):
        info = lookup_model(model_id)
        assert info is not None, f"missing ModelInfo for {model_id}"
        assert info.supports_adaptive_thinking is True
        assert info.supports_extended_thinking is False
        assert ThinkingSignatureDetector().applies_to(model_id) is True

    # Ensure claude-opus-5 does not accidentally resolve to claude-opus-5-5
    assert lookup_model("claude-opus-5").alias == "claude-opus-5"
    assert lookup_model("claude-opus-5.5").alias == "claude-opus-5-5"


def test_claude_5_strips_deprecated_sampling_params():
    body = {"model": "claude-opus-5.5", "temperature": 0.2, "top_p": 0.9, "top_k": 40}
    sanitized = sanitize_anthropic_body(dict(body))
    assert "temperature" not in sanitized
    assert "top_p" not in sanitized
    assert "top_k" not in sanitized


def test_probe_classify_excludes_media_and_video_models():
    assert _classify("clodex-video/gemini-omni-1.2-flash") is None
    assert _classify("gpt-image-2.6") is None
    assert _classify("gemini-4-neon") == "gemini"
    assert _classify("gpt-6.2-astra") == "openai"
    assert _classify("claude-opus-5.5") == "anthropic"


@pytest.mark.parametrize("locale", ["ru", "en", "zh"])
def test_seo_meta_includes_model_and_falls_back_cleanly(locale: str):
    with_model = _seo_meta_for_report(_sample_report(target_model="claude-opus-5-5"), locale)
    assert "claude-opus-5-5" in with_model["seo_title"]
    assert "clodex.xyz" in with_model["seo_title"]
    assert len(with_model["seo_title"]) <= 155

    without_model = _seo_meta_for_report(_sample_report(target_model=""), locale)
    assert "  " not in without_model["seo_title"]
    assert "clodex.xyz" in without_model["seo_title"]
    assert with_model["seo_title"] != without_model["seo_title"]


@pytest.mark.parametrize("locale", ["ru", "en", "zh"])
def test_render_report_jpg_produces_valid_jpeg(locale: str):
    data = render_report_jpg(_sample_report(), locale=locale)
    assert data[:3] == b"\xff\xd8\xff"
    assert len(data) > 10_000


def test_web_routes_render_clodex_dark_theme_without_leaderboard_or_tracker():
    client = TestClient(app)
    for path in ("/", "/claude", "/openai", "/gemini", "/faq"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        assert "G-LWRPQF2182" not in resp.text, f"upstream GA tracker leaked on {path}"
        assert "clodex-logo-header.png" in resp.text
        assert "/leaderboard" not in resp.text, f"leaderboard link leaked on {path}"
        assert 'name="theme-color" content="#080b09"' in resp.text

    # Leaderboard pages must be removed (404)
    assert client.get("/leaderboard").status_code == 404
    assert client.get("/leaderboard/clodex.xyz").status_code == 404

    claude_html = client.get("/claude").text
    assert 'data-preset-url="https://clodex.xyz"' in claude_html
    assert "claude-sonnet-5-5" in claude_html

    openai_html = client.get("/openai").text
    assert 'data-preset-url="https://clodex.xyz/v1"' in openai_html
    assert "gpt-6.2-sol" in openai_html

    gemini_html = client.get("/gemini").text
    assert 'data-preset-url="https://clodex.xyz/v1"' in gemini_html
    assert "gemini-4-neon" in gemini_html

    # Locale cookie persists across navigation
    en_resp = client.get("/?lang=en")
    assert en_resp.status_code == 200
    assert 'lang="en-US"' in en_resp.text
    follow_resp = client.get("/claude")
    assert 'lang="en-US"' in follow_resp.text

    assert client.get("/healthz").json()["ok"] is True
    assert client.get("/robots.txt").status_code == 200
    sitemap_resp = client.get("/sitemap.xml")
    assert sitemap_resp.status_code == 200
    assert "/leaderboard" not in sitemap_resp.text


@pytest.mark.parametrize("locale", ["ru", "en", "zh"])
@pytest.mark.parametrize("protocol", ["anthropic", "openai", "gemini"])
def test_detector_criteria_covers_every_detector(locale: str, protocol: str):
    from web.i18n import detector_criteria, detector_display

    criteria = detector_criteria(locale, protocol)
    for key, _label in detector_display(locale, protocol):
        assert key in criteria and len(criteria[key]) >= 20


def test_running_page_and_status_expose_live_events_and_criteria():
    from web import jobs

    job_id = "testlive1"
    jobs._JOBS[job_id] = jobs.Job(
        id=job_id,
        protocol="anthropic",
        status="running",
        base_url="https://clodex.xyz",
        target_model="claude-sonnet-5-5",
        mode="full",
        started_at=1000.0,
        detector_order=["thinking_signature", "structured_output"],
        detectors={
            "thinking_signature": {
                "name": "thinking_signature",
                "kind": "active",
                "weight": 25.0,
                "status": "pass",
                "score": 100.0,
                "duration_ms": 4200,
                "summary": "signature 1036 B",
                "error": None,
            },
            "structured_output": {
                "name": "structured_output",
                "kind": "active",
                "weight": 12.0,
                "status": "running",
                "score": None,
                "duration_ms": None,
                "summary": "",
                "error": None,
            },
        },
        events=[
            {"ts_ms": 0, "type": "run_start", "model": "claude-sonnet-5-5", "mode": "full"},
            {
                "ts_ms": 4200,
                "type": "detector_done",
                "name": "thinking_signature",
                "status": "pass",
                "score": 100.0,
                "duration_ms": 4200,
                "summary": "signature 1036 B",
            },
        ],
    )
    try:
        client = TestClient(app)
        status_resp = client.get(f"/api/status/{job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["progress"] == {"completed": 1, "total": 2}
        assert len(data["detectors"]) == 2
        assert len(data["events"]) == 2
        assert data["detectors"][0]["summary"] == "signature 1036 B"

        page_resp = client.get(f"/r/{job_id}")
        assert page_resp.status_code == 200
        assert "live-log-terminal" in page_resp.text
        assert "live-check-list" in page_resp.text
        assert "signature 500–2000" in page_resp.text
    finally:
        jobs._JOBS.pop(job_id, None)


def test_knowledge_parser_handles_bold_markdown_numbers():
    from relay_detector.protocols.anthropic.detectors.knowledge import _parse_numbered_answers

    parsed = _parse_numbered_answers(
        "1. Dario Amodei\n**2.** Daniela Amodei\n- 3. Principles\n**4.** 2023\n5. San Francisco",
        5,
    )
    assert parsed[2] == "Daniela Amodei"
    assert parsed[3] == "Principles"
    assert parsed[4] == "2023"

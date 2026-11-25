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

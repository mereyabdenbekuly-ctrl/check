"""Comprehensive SEO & AI GEO tests: JSON-LD validity, hreflang, canonical, robots, sitemap, OG cover."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from web import jobs
from web.server import app


_JSONLD_RE = re.compile(
    r'<script\s+type="application/ld\+json"\s*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_jsonld_blocks(html: str) -> list[dict]:
    blocks = []
    for raw in _JSONLD_RE.findall(html):
        parsed = json.loads(raw.strip())
        assert isinstance(parsed, dict)
        blocks.append(parsed)
    return blocks


def test_all_primary_pages_have_valid_jsonld_hreflang_canonical_and_og_cover():
    client = TestClient(app)
    for path in ("/", "/claude", "/openai", "/gemini", "/pelican", "/compare", "/faq"):
        for lang_qs, expected_canonical in (
            ("", f"https://check.clodex.xyz{path}"),
            ("?lang=en", f"https://check.clodex.xyz{path}?lang=en"),
            ("?lang=zh", f"https://check.clodex.xyz{path}?lang=zh"),
        ):
            client.cookies.clear()
            r = client.get(path + lang_qs)
            assert r.status_code == 200, f"failed on {path}{lang_qs}"
            html = r.text
            assert f'<link rel="canonical" href="{expected_canonical}"' in html
            assert f'hreflang="ru" href="https://check.clodex.xyz{path}"' in html
            assert f'hreflang="en" href="https://check.clodex.xyz{path}?lang=en"' in html
            assert f'hreflang="zh-Hans" href="https://check.clodex.xyz{path}?lang=zh"' in html
            assert f'hreflang="x-default" href="https://check.clodex.xyz{path}"' in html
            assert "https://check.clodex.xyz/static/og-cover.png" in html
            assert 'property="og:image:width" content="1200"' in html
            assert 'property="og:image:height" content="630"' in html
            assert html.count("<main") == 1, f"nested <main> detected on {path}"
            blocks = _extract_jsonld_blocks(html)
            assert len(blocks) >= 1, f"missing JSON-LD on {path}{lang_qs}"


def test_ru_redirects_permanently_to_root():
    client = TestClient(app)
    r = client.get("/ru", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/"


def test_noindex_rules_for_running_compare_query_error_report_and_api():
    client = TestClient(app)

    # /compare with query params must be noindex,follow to prevent crawler traps
    r_cmp = client.get("/compare?a=abc12345&b=def67890")
    assert r_cmp.status_code == 200
    assert '<meta name="robots" content="noindex,follow"' in r_cmp.text

    # API & healthz carry X-Robots-Tag: noindex, nofollow
    hz = client.get("/healthz")
    assert hz.status_code == 200
    assert hz.headers.get("x-robots-tag") == "noindex, nofollow"

    # Running job page must be noindex,nofollow
    jobs._JOBS["runseo12"] = jobs.Job(
        id="runseo12", protocol="anthropic", status="running", base_url="https://clodex.xyz", target_model="claude-sonnet-5-5"
    )
    # Error report must also be noindex,nofollow; clean report must be indexable with TechArticle JSON-LD
    jobs._JOBS["errseo12"] = jobs.Job(
        id="errseo12",
        protocol="anthropic",
        status="done",
        base_url="https://clodex.xyz",
        target_model="claude-sonnet-5-5",
        report={
            "protocol": "anthropic",
            "base_url": "https://clodex.xyz",
            "target_model": "claude-sonnet-5-5",
            "mode": "full",
            "total_score": 0.0,
            "verdict": "failed",
            "run_error": "HTTP 401 invalid key",
            "results": [],
            "performance": {},
        },
    )
    jobs._JOBS["okseo123"] = jobs.Job(
        id="okseo123",
        protocol="anthropic",
        status="done",
        base_url="https://clodex.xyz",
        target_model="claude-sonnet-5-5",
        report={
            "protocol": "anthropic",
            "base_url": "https://clodex.xyz",
            "target_model": "claude-sonnet-5-5",
            "mode": "full",
            "timestamp": "2026-11-25T10:00:00+00:00",
            "total_score": 100.0,
            "verdict": "passed",
            "results": [{"name": "thinking_signature", "status": "pass", "score": 100.0}],
            "performance": {},
        },
    )
    try:
        r_run = client.get("/r/runseo12")
        assert r_run.status_code == 200
        assert '<meta name="robots" content="noindex,nofollow"' in r_run.text

        r_err = client.get("/r/errseo12")
        assert r_err.status_code == 200
        assert '<meta name="robots" content="noindex,nofollow"' in r_err.text

        r_ok = client.get("/r/okseo123")
        assert r_ok.status_code == 200
        assert '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1"' in r_ok.text
        blocks = _extract_jsonld_blocks(r_ok.text)
        assert len(blocks) == 1
        assert any(node.get("@type") == "TechArticle" for node in blocks[0]["@graph"])
    finally:
        for jid in ("runseo12", "errseo12", "okseo123"):
            jobs._JOBS.pop(jid, None)


def test_robots_sitemap_hreflang_and_llms_full(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    from web import server as srv

    monkeypatch.setattr(
        srv,
        "_SITEMAP_REPORT_DIRS",
        [tmp_path / "anthropic", tmp_path / "openai", tmp_path / "gemini", tmp_path],
    )
    # Write one clean public report, one broken report, and one localhost report
    (tmp_path / "anthropic").mkdir(parents=True)
    (tmp_path / "anthropic" / "clean123.json").write_text(
        json.dumps({"base_url": "https://clodex.xyz", "total_score": 100.0}),
        encoding="utf-8",
    )
    (tmp_path / "anthropic" / "broken99.json").write_text(
        json.dumps({"base_url": "https://clodex.xyz", "run_error": "HTTP 401"}),
        encoding="utf-8",
    )
    (tmp_path / "anthropic" / "local777.json").write_text(
        json.dumps({"base_url": "http://127.0.0.1:8080", "total_score": 90.0}),
        encoding="utf-8",
    )

    client = TestClient(app)

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "User-agent: Yandex" in robots.text
    assert "Clean-param: tab&a&b /" in robots.text
    assert "Host: https://check.clodex.xyz" in robots.text

    llms = client.get("/llms.txt")
    assert llms.status_code == 200
    assert "llms-full.txt" in llms.text

    llms_full = client.get("/llms-full.txt")
    assert llms_full.status_code == 200
    assert "thinking_signature" in llms_full.text

    og = client.get("/static/og-cover.png")
    assert og.status_code == 200
    assert og.content[:8] == b"\x89PNG\r\n\x1a\n"

    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200
    root = ET.fromstring(sm.text)
    assert root.tag.endswith("urlset")
    assert "https://check.clodex.xyz/pelican" in sm.text
    assert "https://check.clodex.xyz/compare" in sm.text
    assert 'hreflang="zh-Hans"' in sm.text
    assert "clean123" in sm.text
    assert "broken99" not in sm.text
    assert "local777" not in sm.text

"""Clodex FastAPI app — POST /api/detect, GET /r/{id}, GET /r/{id}.jpg."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi import Response as FastAPIResponse
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import jobs
from .i18n import (
    detect_locale,
    detector_criteria,
    detector_display,
    detector_labels_map,
    html_lang,
    og_locale,
    lt,
    result_caption,
    status_short,
    t as tr,
    tier_banner_for_locale,
    ui as ui_copy,
    with_lang,
)
from .faq_data import categories as faq_categories, faqpage_jsonld, total_question_count
from .image_report import render_report_jpg
from .probe import is_dns_resolution_error, probe_model_alive, probe_relay
from .ratelimit import check_rate


HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"

logger = logging.getLogger("clodex_check")
logger.setLevel(logging.INFO)

app = FastAPI(title="Clodex", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals.update(with_lang=with_lang, tr=tr, lt=lt)


_SITE_ORIGIN = "https://check.clodex.xyz"


def _page_ctx(request: Request, **context: object) -> dict[str, object]:
    locale = detect_locale(request)
    raw_path = str(context.get("seo_path") or request.url.path or "/")
    if raw_path == "/ru":
        raw_path = "/"
    base_canonical = f"{_SITE_ORIGIN}{raw_path}"
    seo_canonical = with_lang(base_canonical, locale)
    hreflang_links = [
        ("ru", base_canonical),
        ("en", with_lang(base_canonical, "en")),
        ("zh-Hans", with_lang(base_canonical, "zh")),
        ("x-default", base_canonical),
    ]
    og_alt_locales = [og_locale(loc) for loc in ("ru", "en", "zh") if loc != locale]
    payload: dict[str, object] = {
        "locale": locale,
        "ui": ui_copy(locale),
        "html_lang": html_lang(locale),
        "og_locale": og_locale(locale),
        "og_alt_locales": og_alt_locales,
        "seo_canonical": seo_canonical,
        "hreflang_links": hreflang_links,
        "lang": locale,
    }
    payload.update(context)
    return payload


def _render(request: Request, template_name: str, **context: object) -> HTMLResponse:
    response = templates.TemplateResponse(
        request,
        template_name,
        _page_ctx(request, **context),
    )
    response.set_cookie(
        "lang",
        detect_locale(request),
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
    )
    return response


@app.middleware("http")
async def no_html_cache(request: Request, call_next):
    """Manage HTTP cache headers and crawler hints.

    - HTML pages use `no-cache, must-revalidate` so updates appear immediately.
    - Versioned `/static/*?v=...` assets get immutable 1-year browser caching.
    - `/api/*` and `/healthz` carry `X-Robots-Tag: noindex, nofollow`.
    """
    response = await call_next(request)
    path = request.url.path
    ctype = response.headers.get("content-type", "")
    if ctype.startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif path.startswith("/static/") and "v" in request.query_params:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    if path.startswith("/api/") or path == "/healthz":
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


_VALID_MODES = {"quick", "standard", "full"}
_VALID_WISHLIST_PROTOCOLS = {"openai", "gemini"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WISHLIST_PATH = Path(
    os.environ.get("CLODEX_CHECK_WISHLIST_PATH", "/opt/clodex-check/web_data/wishlist.txt")
)


def _protocol_from_model(model: str) -> str:
    normalized = model.strip().lower()
    if normalized.startswith(("gemini-", "models/gemini-")):
        return "gemini"
    if normalized.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return "anthropic"


def _model_choices() -> list[dict[str, str]]:
    """Curated dropdown — current flagship + stable Claude models. Free-form
    input still accepts anything; lookup_model() matches snapshot/alias forms.
    """
    suggestions = [
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]
    return [{"id": s, "label": s} for s in suggestions]


def _openai_model_choices() -> list[dict[str, str]]:
    from relay_detector.protocols.openai import model_choices

    return [{"id": s, "label": s} for s in model_choices()]


def _gemini_model_choices() -> list[dict[str, str]]:
    from relay_detector.protocols.gemini import model_choices

    return [{"id": s, "label": s} for s in model_choices()]


@app.get("/", response_class=HTMLResponse)
async def hub(request: Request) -> HTMLResponse:
    return _render(request, "hub.html")


@app.get("/ru")
async def hub_ru() -> RedirectResponse:
    """Permanent redirect to canonical root to avoid duplicate indexing."""
    return RedirectResponse(url="/", status_code=301)


@app.get("/claude", response_class=HTMLResponse)
async def claude_index(request: Request) -> HTMLResponse:
    return _render(request, "index.html", models=_model_choices())


@app.get("/openai", response_class=HTMLResponse)
async def openai_index(request: Request) -> HTMLResponse:
    return _render(request, "openai.html", models=_openai_model_choices())


@app.get("/gemini", response_class=HTMLResponse)
async def gemini_index(request: Request) -> HTMLResponse:
    return _render(request, "gemini.html", models=_gemini_model_choices())


@app.get("/pelican", response_class=HTMLResponse)
async def pelican_page(request: Request, protocol: str = "anthropic") -> HTMLResponse:
    from relay_detector.core.pelican import PELICAN_PROMPT

    p = (protocol or "anthropic").strip().lower()
    if p == "claude":
        p = "anthropic"
    if p not in {"anthropic", "openai", "gemini"}:
        p = "anthropic"
    return _render(
        request,
        "pelican.html",
        initial_protocol=p,
        models_by_protocol={
            "anthropic": [m["id"] for m in _model_choices()],
            "openai": [m["id"] for m in _openai_model_choices()],
            "gemini": [m["id"] for m in _gemini_model_choices()],
        },
        pelican_prompt=PELICAN_PROMPT,
    )


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,40}$")


def _extract_job_id(raw: str | None) -> str:
    """Normalize a pasted job ID or full /r/{id} URL into a safe job ID."""
    val = (raw or "").strip()
    if not val:
        return ""
    val = val.split("#", 1)[0].split("?", 1)[0].strip().rstrip("/")
    if "/r/" in val:
        val = val.split("/r/", 1)[1]
        val = val.split("/", 1)[0]
    for suffix in (".jpg", ".json", ".svg"):
        if val.endswith(suffix):
            val = val[: -len(suffix)]
    val = val.strip()
    return val if _JOB_ID_RE.match(val) else ""


def _domain_from_url(base_url: str, fallback: str) -> str:
    if not base_url:
        return fallback
    if "://" in base_url:
        return base_url.split("://", 1)[1].split("/", 1)[0] or fallback
    return base_url.split("/", 1)[0] or fallback


def _verdict_css_class(score: float, verdict: str) -> str:
    if verdict == "passed" and score >= 85:
        return "ok"
    if verdict == "passed":
        return "ok-dim"
    if verdict == "marginal":
        return "warn"
    return "fail"


def _compare_summary(job_id: str, report: dict, locale: str) -> dict:
    protocol = str(report.get("protocol") or "anthropic")
    score = float(report.get("total_score") or 0.0)
    verdict = str(report.get("verdict") or "failed")
    perf = report.get("performance") or {}
    usage = perf.get("usage") or {}
    sa = perf.get("stream_analysis") if isinstance(perf.get("stream_analysis"), dict) else {}
    tps = perf.get("tokens_per_second")
    if not isinstance(tps, (int, float)) or tps <= 0:
        out_t = usage.get("output_tokens") or 0
        lat = perf.get("total_latency_ms") or 0
        tps = round(out_t * 1000.0 / lat, 1) if (out_t and lat) else None
    else:
        tps = round(float(tps), 1)
    results = [r for r in (report.get("results") or []) if isinstance(r, dict)]
    ran = [r for r in results if r.get("status") != "skip"]
    passed = sum(1 for r in ran if r.get("status") == "pass")
    failed = sum(1 for r in ran if r.get("status") in {"fail", "error"})
    return {
        "job_id": job_id,
        "protocol": protocol,
        "proto_label": _PROTOCOL_LABELS.get(protocol, protocol),
        "base_url": str(report.get("base_url") or ""),
        "domain": _domain_from_url(str(report.get("base_url") or ""), tr(locale, "relay_fallback")),
        "target_model": str(report.get("target_model") or ""),
        "mode": str(report.get("mode") or ""),
        "score": score,
        "verdict": verdict,
        "verdict_class": _verdict_css_class(score, verdict),
        "caption": result_caption(locale, score, verdict, protocol),
        "ttft_ms": perf.get("ttft_ms"),
        "total_latency_ms": perf.get("total_latency_ms") or 0,
        "tokens_per_second": tps,
        "stream_verdict": sa.get("verdict") or "",
        "stream_chunks": sa.get("chunk_count") or 0,
        "input_tokens": usage.get("input_tokens") or 0,
        "output_tokens": usage.get("output_tokens") or 0,
        "passed": passed,
        "failed": failed,
        "ran_total": len(ran),
        "pelican": _pelican_preview(report),
    }


def _row_status_tuple(r: dict | None, name: str, locale: str) -> tuple[str, str, str, float | None, str]:
    if not r:
        return ("absent", "—", "muted", None, "")
    status = str(r.get("status") or "skip")
    score = float(r.get("score") or 0.0)
    summary = jobs._summarize_detector_result(name, status, r.get("details"), r.get("error"))
    if status == "pass":
        return (status, status_short(locale, "pass", name), "ok", score, summary)
    if status == "skip":
        return (status, status_short(locale, "skip", name), "muted", None, summary)
    if status == "error":
        return (status, status_short(locale, "error", name), "fail", score, summary)
    if score >= 70:
        return (status, status_short(locale, "warn", name), "warn", score, summary)
    return (status, status_short(locale, "fail", name), "fail", score, summary)


def _compare_rows(report_a: dict, report_b: dict, locale: str) -> list[dict]:
    proto_a = str(report_a.get("protocol") or "anthropic")
    proto_b = str(report_b.get("protocol") or "anthropic")
    by_a = {r.get("name"): r for r in (report_a.get("results") or []) if isinstance(r, dict)}
    by_b = {r.get("name"): r for r in (report_b.get("results") or []) if isinstance(r, dict)}

    labels: dict[str, str] = {}
    order: list[str] = []
    for proto in (proto_a, proto_b):
        for name, label in detector_display(locale, proto):
            if name not in labels:
                labels[name] = label
                order.append(name)
    for name in list(by_a.keys()) + list(by_b.keys()):
        if isinstance(name, str) and name not in labels:
            labels[name] = name
            order.append(name)

    rows: list[dict] = []
    for name in order:
        ra = by_a.get(name)
        rb = by_b.get(name)
        if name == "long_context":
            sa_st = (ra or {}).get("status", "skip")
            sb_st = (rb or {}).get("status", "skip")
            if sa_st == "skip" and sb_st == "skip":
                continue
        if ra is None and rb is None:
            continue
        a_st, a_short, a_css, a_score, a_sum = _row_status_tuple(ra, name, locale)
        b_st, b_short, b_css, b_score, b_sum = _row_status_tuple(rb, name, locale)
        winner = "na"
        delta: float | None = None
        if a_score is not None and b_score is not None:
            delta = round(b_score - a_score, 1)
            if abs(delta) < 0.5:
                winner = "tie"
            elif delta > 0:
                winner = "b"
            else:
                winner = "a"
        rows.append({
            "name": name,
            "label": labels[name],
            "a_status": a_st,
            "a_short": a_short,
            "a_css": a_css,
            "a_score": a_score,
            "a_summary": a_sum,
            "b_status": b_st,
            "b_short": b_short,
            "b_css": b_css,
            "b_score": b_score,
            "b_summary": b_sum,
            "delta": delta,
            "winner": winner,
        })
    return rows


@app.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request, a: str = "", b: str = "") -> HTMLResponse:
    locale = detect_locale(request)
    raw_a = a.strip()
    raw_b = b.strip()
    id_a = _extract_job_id(raw_a)
    id_b = _extract_job_id(raw_b)

    errors: list[str] = []
    job_a = await jobs.get(id_a) if id_a else None
    job_b = await jobs.get(id_b) if id_b else None

    if raw_a and (not id_a or job_a is None or job_a.status != "done" or job_a.report is None):
        errors.append(
            lt(
                locale,
                f"Отчёт A («{raw_a[:48]}») не найден или ещё не завершён.",
                f"Report A ('{raw_a[:48]}') was not found or is still running.",
                f"未找到报告 A（{raw_a[:48]}），或该检测尚未完成。",
            )
        )
    if raw_b and (not id_b or job_b is None or job_b.status != "done" or job_b.report is None):
        errors.append(
            lt(
                locale,
                f"Отчёт B («{raw_b[:48]}») не найден или ещё не завершён.",
                f"Report B ('{raw_b[:48]}') was not found or is still running.",
                f"未找到报告 B（{raw_b[:48]}），或该检测尚未完成。",
            )
        )

    summary_a = None
    summary_b = None
    diff_rows: list[dict] = []
    score_delta: float | None = None
    if (
        job_a is not None
        and job_b is not None
        and job_a.status == "done"
        and job_b.status == "done"
        and job_a.report is not None
        and job_b.report is not None
    ):
        summary_a = _compare_summary(id_a, job_a.report, locale)
        summary_b = _compare_summary(id_b, job_b.report, locale)
        diff_rows = _compare_rows(job_a.report, job_b.report, locale)
        score_delta = round(summary_b["score"] - summary_a["score"], 1)

    return _render(
        request,
        "compare.html",
        raw_a=id_a or raw_a,
        raw_b=id_b or raw_b,
        errors=errors,
        summary_a=summary_a,
        summary_b=summary_b,
        diff_rows=diff_rows,
        score_delta=score_delta,
    )


@app.get("/faq", response_class=HTMLResponse)
async def faq_index(request: Request) -> HTMLResponse:
    """Standalone FAQ page — single source of truth in faq_data.py drives
    both the rendered HTML and the FAQPage JSON-LD schema in <head>."""
    return _render(
        request,
        "faq.html",
        categories=faq_categories(detect_locale(request)),
        total_count=total_question_count(detect_locale(request)),
        jsonld=json.dumps(faqpage_jsonld(detect_locale(request)), ensure_ascii=False),
    )


@app.post("/api/wishlist")
async def api_wishlist(
    email: str = Form(...),
    protocol: str = Form(...),
) -> JSONResponse:
    email = email.strip()
    protocol = protocol.strip().lower()
    if protocol not in _VALID_WISHLIST_PROTOCOLS:
        raise HTTPException(status_code=400, detail="unsupported protocol")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="email looks invalid")

    WISHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"ts": int(time.time()), "protocol": protocol, "email": email},
        ensure_ascii=False,
    )
    with WISHLIST_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return JSONResponse({"ok": True})


def _client_ip(request: Request) -> str:
    """Resolve the originating client IP.

    uvicorn is started with --proxy-headers --forwarded-allow-ips=* so by the
    time FastAPI sees the request, request.client.host is already the leftmost
    X-Forwarded-For value (the real client). Fall back to "unknown" if the
    request somehow lacks a client (shouldn't happen behind Caddy).
    """
    return request.client.host if request.client else "unknown"


# Probe is cheap (one upstream GET) but accepts arbitrary base_url + api_key,
# making it a tempting key-scanning oracle. 15/min/IP is generous enough for
# a real user editing/correcting fields and tight enough to slow scanners.
# Preflight (per-model alive check) shares the same bucket — both are "fan
# one cheap upstream call out from this proxy" operations.
_PROBE_RATE_LIMIT = 15
_PROBE_RATE_WINDOW_S = 60.0


async def _preflight_or_422(
    request: Request,
    base_url: str,
    api_key: str,
    model: str,
    protocol: str,
) -> None:
    """Run model-alive preflight; raise HTTPException 422 with structured
    detail if the model is dead so the frontend can offer a one-click swap
    to the protocol's recommended model.

    Honors the same per-IP probe rate limit. force=true on the request body
    skips preflight entirely (escape hatch when relays false-negative on
    our 4-token ping).
    """
    form = await request.form()
    if str(form.get("force") or "").lower() in ("1", "true", "yes"):
        return

    ip = _client_ip(request)
    allowed, retry_after = check_rate(
        ip, limit=_PROBE_RATE_LIMIT, window_s=_PROBE_RATE_WINDOW_S
    )
    if not allowed:
        # Rate limited preflight — DON'T block submission. The detector
        # itself will surface the model_not_found if there is one; we just
        # skip the early-warning path until backoff expires.
        return

    alive, err = await probe_model_alive(base_url, api_key, model, protocol)
    if alive:
        return
    if alive is None:
        if is_dns_resolution_error(err):
            host = (urlparse(base_url).hostname or base_url).strip()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Домен {host} не найден (DNS). "
                    "Проверьте правильность Base URL (например https://clodex.xyz)."
                ),
            )
        # Transport uncertainty (timeout/network blip) must not block the
        # real detector run. Slow frontier models such as GPT-5.5 can exceed
        # the tiny preflight budget while still working in the full check.
        return

    raise HTTPException(
        status_code=422,
        detail={
            "code": "model_not_alive",
            "message": (
                f"模型 {model} 在该relay实际不可用。relay把它列在 /v1/models "
                "里,但真实请求被上游拒绝。"
            ),
            "model": model,
            "protocol": protocol,
            "upstream_error": err or "",
        },
    )


@app.post("/api/probe")
async def api_probe(
    request: Request,
    base_url: str = Form(...),
    api_key: str = Form(...),
    protocol: str | None = Form(None),
) -> JSONResponse:
    """Probe a relay's /v1/models for the form's pre-submit pill.

    Always returns 200 with a structured payload — the frontend renders any
    upstream error inline rather than as a fetch failure. Exception: a 429
    is returned (with Retry-After) when the per-IP rate limit is exhausted,
    so the browser can back off and the frontend can show a clear "too
    many probes" pill instead of a generic upstream error.
    """
    ip = _client_ip(request)
    allowed, retry_after = check_rate(
        ip, limit=_PROBE_RATE_LIMIT, window_s=_PROBE_RATE_WINDOW_S
    )
    if not allowed:
        wait = int(retry_after) + 1
        return JSONResponse(
            {
                "ok": False,
                "auth_ok": True,
                "error": f"探测过于频繁,请在 {wait} 秒后再试",
                "rate_limited": True,
            },
            status_code=429,
            headers={"Retry-After": str(wait)},
        )

    base_url = base_url.strip()
    api_key = api_key.strip()

    if not base_url.startswith(("http://", "https://")):
        return JSONResponse(
            {"ok": False, "error": "base_url must start with http(s)://"},
            status_code=200,
        )
    if not api_key or len(api_key) < 8:
        return JSONResponse(
            {"ok": False, "error": "api_key looks invalid"},
            status_code=200,
        )

    payload = await probe_relay(base_url, api_key, protocol=protocol)
    return JSONResponse(payload)


@app.post("/api/detect")
@app.post("/api/detect/claude")
async def api_detect_claude(
    request: Request,
    response: FastAPIResponse,
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    mode: str = Form("full"),
    include_long_context: bool = Form(False),
    include_long_context_extreme: bool = Form(False),
) -> JSONResponse:
    base_url = base_url.strip()
    api_key = api_key.strip()
    model = model.strip()
    mode = mode.strip().lower()

    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url must start with http(s)://")
    if not api_key or len(api_key) < 8:
        raise HTTPException(status_code=400, detail="api_key looks invalid")
    # Permissive model validation: relays often expose custom names like
    # "claude-opus-4-7-thinking" or vendor-prefixed variants. Detectors
    # use lookup_model() which does double-prefix matching and gracefully
    # skips thinking/PDF probes for unknown models, so we let anything
    # reasonable through and let the upstream relay decide what's valid.
    if not model or len(model) > 200:
        raise HTTPException(status_code=400, detail="model must be 1–200 chars")
    if mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {_VALID_MODES}")

    if request.url.path == "/api/detect":
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = '</api/detect/claude>; rel="successor-version"'
        inferred = _protocol_from_model(model)
        if inferred != "anthropic":
            await _preflight_or_422(request, base_url, api_key, model, inferred)
            job_id = await jobs.submit(
                base_url, api_key, model, mode,
                protocol=inferred,
                include_long_context=include_long_context,
                include_long_context_extreme=include_long_context_extreme,
            )
            return JSONResponse({"job_id": job_id, "status_url": f"/api/status/{job_id}"})
    elif _protocol_from_model(model) == "gemini":
        raise HTTPException(
            status_code=400,
            detail="这是 Gemini 模型,请在 /gemini 页面提交检测。",
        )
    elif _protocol_from_model(model) == "openai":
        raise HTTPException(
            status_code=400,
            detail="这是 OpenAI 模型,请在 /openai 页面提交检测。",
        )

    await _preflight_or_422(request, base_url, api_key, model, "anthropic")
    job_id = await jobs.submit(
        base_url, api_key, model, mode,
        protocol="anthropic",
        include_long_context=include_long_context,
        include_long_context_extreme=include_long_context_extreme,
    )
    # NOTE: never echo api_key back in the response
    return JSONResponse({"job_id": job_id, "status_url": f"/api/status/{job_id}"})


@app.post("/api/detect/openai")
async def api_detect_openai(
    request: Request,
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    mode: str = Form("standard"),
    include_long_context: bool = Form(False),
    include_long_context_extreme: bool = Form(False),
) -> JSONResponse:
    base_url = base_url.strip()
    api_key = api_key.strip()
    model = model.strip()
    mode = mode.strip().lower()

    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url must start with http(s)://")
    if not api_key or len(api_key) < 8:
        raise HTTPException(status_code=400, detail="api_key looks invalid")
    if not model or len(model) > 200:
        raise HTTPException(status_code=400, detail="model must be 1–200 chars")
    if mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {_VALID_MODES}")

    await _preflight_or_422(request, base_url, api_key, model, "openai")
    job_id = await jobs.submit(
        base_url, api_key, model, mode,
        protocol="openai",
        include_long_context=include_long_context,
        include_long_context_extreme=include_long_context_extreme,
    )
    return JSONResponse({"job_id": job_id, "status_url": f"/api/status/{job_id}"})


@app.post("/api/detect/gemini")
async def api_detect_gemini(
    request: Request,
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    mode: str = Form("standard"),
) -> JSONResponse:
    base_url = base_url.strip()
    api_key = api_key.strip()
    model = model.strip()
    mode = mode.strip().lower()

    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url must start with http(s)://")
    if not api_key or len(api_key) < 8:
        raise HTTPException(status_code=400, detail="api_key looks invalid")
    if not model or len(model) > 200:
        raise HTTPException(status_code=400, detail="model must be 1–200 chars")
    if mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {_VALID_MODES}")

    await _preflight_or_422(request, base_url, api_key, model, "gemini")
    job_id = await jobs.submit(base_url, api_key, model, mode, protocol="gemini")
    return JSONResponse({"job_id": job_id, "status_url": f"/api/status/{job_id}"})


def _validate_pelican_request(
    request: Request,
    protocol: str,
    base_url: str,
    api_key: str,
    model: str,
    reasoning_effort: str,
) -> tuple[str, str, str, str, str]:
    ip = _client_ip(request)
    allowed, retry_after = check_rate(ip, limit=20, window_s=60.0)
    if not allowed:
        wait = int(retry_after) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many Pelican requests, retry in {wait}s",
            headers={"Retry-After": str(wait)},
        )

    proto = (protocol or "anthropic").strip().lower()
    if proto == "claude":
        proto = "anthropic"
    if proto not in {"anthropic", "openai", "gemini"}:
        raise HTTPException(status_code=400, detail="protocol must be anthropic, openai, or gemini")

    base_url = base_url.strip()
    api_key = api_key.strip()
    model = model.strip()
    effort = (reasoning_effort or "auto").strip().lower()
    if effort not in {"auto", "low", "medium", "high", "xhigh", "max", "none", "off", "default"}:
        effort = "auto"

    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url must start with http(s)://")
    if not api_key or len(api_key) < 8:
        raise HTTPException(status_code=400, detail="api_key looks invalid")
    if not model or len(model) > 200:
        raise HTTPException(status_code=400, detail="model must be 1–200 chars")
    return proto, base_url, api_key, model, effort


def _pelican_json_payload(job_id: str, report: dict) -> dict:
    pelican = _pelican_preview(report) or {}
    pelican_public = {k: v for k, v in pelican.items() if k != "svg_raw"}
    # NOTE: never echo api_key back in the response
    return {
        "ok": bool(pelican_public.get("valid_svg")),
        "job_id": job_id,
        "protocol": report.get("protocol", "anthropic"),
        "model": report.get("target_model", ""),
        "base_url": report.get("base_url", ""),
        "total_score": report.get("total_score", 0.0),
        "verdict": report.get("verdict", "failed"),
        "error": report.get("run_error"),
        "pelican": pelican_public,
        "performance": report.get("performance") or {},
        "result_url": f"/r/{job_id}",
        "svg_url": f"/r/{job_id}/pelican.svg",
        "jpg_url": f"/r/{job_id}.jpg",
        "compare_url": f"/compare?a={job_id}",
    }


@app.post("/api/pelican/start")
async def api_pelican_start(
    request: Request,
    protocol: str = Form("anthropic"),
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    reasoning_effort: str = Form("auto"),
) -> JSONResponse:
    """Queue an async Pelican SVG run and return immediately so long
    high-reasoning generations never hit 120s gateway 504 timeouts."""
    proto, base_url, api_key, model, effort = _validate_pelican_request(
        request, protocol, base_url, api_key, model, reasoning_effort
    )
    job_id = await jobs.submit_pelican(
        base_url,
        api_key,
        model,
        protocol=proto,
        reasoning_effort=effort,
    )
    return JSONResponse(
        {"job_id": job_id, "status_url": f"/api/pelican/status/{job_id}"},
        status_code=202,
    )


@app.get("/api/pelican/status/{job_id}")
async def api_pelican_status(job_id: str) -> JSONResponse:
    j = await jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    if j.status == "done" and j.report is not None:
        return JSONResponse({"status": "done", **_pelican_json_payload(j.id, j.report)})
    if j.status == "error":
        return JSONResponse({"status": "error", "job_id": j.id, "error": j.error or "Pelican run failed"})
    now = time.time()
    elapsed_ms = (
        max(0, int((now - j.started_at) * 1000))
        if j.started_at is not None
        else 0
    )
    return JSONResponse({"status": j.status, "job_id": j.id, "elapsed_ms": elapsed_ms})


@app.post("/api/pelican")
async def api_pelican(
    request: Request,
    protocol: str = Form("anthropic"),
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
    reasoning_effort: str = Form("auto"),
) -> JSONResponse:
    """Run the standalone Pelican-on-a-bicycle SVG test (single streamed call)."""
    proto, base_url, api_key, model, effort = _validate_pelican_request(
        request, protocol, base_url, api_key, model, reasoning_effort
    )
    job_id, report = await jobs.run_pelican(
        base_url,
        api_key,
        model,
        protocol=proto,
        reasoning_effort=effort,
    )
    return JSONResponse(_pelican_json_payload(job_id, report))


@app.get("/api/status/{job_id}")
async def api_status(job_id: str) -> JSONResponse:
    j = await jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    now = time.time()
    elapsed_ms = (
        max(0, int(((j.finished_at or now) - j.started_at) * 1000))
        if j.started_at is not None
        else 0
    )
    ordered_detectors = [
        j.detectors[name]
        for name in j.detector_order
        if name in j.detectors
    ]
    non_skip = [d for d in ordered_detectors if d.get("kind") != "skip"]
    completed = sum(
        1
        for d in non_skip
        if d.get("status") in {"pass", "fail", "error", "skip"}
    )
    payload = {
        "job_id": j.id,
        "protocol": j.protocol,
        "status": j.status,
        "base_url": j.base_url,
        "target_model": j.target_model,
        "mode": j.mode,
        "created_at": j.created_at,
        "started_at": j.started_at,
        "finished_at": j.finished_at,
        "elapsed_ms": elapsed_ms,
        "progress": {
            "completed": completed,
            "total": len(non_skip),
        },
        "detectors": ordered_detectors,
        "events": j.events[-80:],
    }
    if j.status == "done":
        payload["result_url"] = f"/r/{j.id}"
        payload["image_url"] = f"/r/{j.id}.jpg"
        payload["json_url"] = f"/api/result/{j.id}.json"
    elif j.status == "error":
        payload["error"] = j.error
    return JSONResponse(payload)


@app.get("/api/result/{job_id}.json")
async def api_result_json(job_id: str) -> JSONResponse:
    j = await jobs.get(job_id)
    if j is None or j.report is None:
        raise HTTPException(status_code=404, detail="result not ready")
    return JSONResponse(j.report)


# NOTE: declare .jpg route BEFORE the bare /r/{job_id} HTML route. Starlette
# path params match `[^/]+` greedily so `/r/{job_id}` would otherwise swallow
# `/r/foo.jpg` (job_id="foo.jpg") and shadow the image endpoint.
@app.get("/r/{job_id}.jpg")
async def result_jpg(request: Request, job_id: str) -> Response:
    j = await jobs.get(job_id)
    if j is None or j.status != "done" or j.report is None:
        raise HTTPException(status_code=404, detail="result not ready")

    locale = detect_locale(request)
    base_cache = jobs.image_path(job_id, j.protocol)
    cache_path = base_cache.with_name(f"{job_id}.{locale}.v5.jpg")
    if not cache_path.exists():
        jpg_bytes = render_report_jpg(j.report, locale=locale)
        cache_path.write_bytes(jpg_bytes)
    return Response(
        content=cache_path.read_bytes(),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'inline; filename="clodex-check-{job_id}.jpg"',
            "Cache-Control": "public, max-age=86400",
        },
    )


def _pelican_preview(report: dict) -> dict | None:
    """Extract sanitized SVG & metadata from a report's pelican_svg result."""
    for r in report.get("results") or []:
        if not isinstance(r, dict) or r.get("name") != "pelican_svg":
            continue
        status = str(r.get("status") or "skip")
        if status == "skip":
            return None
        d = r.get("details") if isinstance(r.get("details"), dict) else {}
        svg = d.get("svg_sanitized")
        svg_str = svg if isinstance(svg, str) and svg.strip().startswith("<svg") else ""
        svg_b64 = (
            base64.b64encode(svg_str.encode("utf-8")).decode("ascii")
            if svg_str
            else ""
        )
        return {
            "status": status,
            "score": float(r.get("score") or 0.0),
            "valid_svg": bool(d.get("valid_svg")) and bool(svg_str),
            "svg_b64": svg_b64,
            "svg_raw": svg_str,
            "primitive_count": int(d.get("primitive_count") or 0),
            "unique_colors": int(d.get("unique_colors") or 0),
            "svg_bytes": int(d.get("svg_bytes") or 0),
            "view_box": str(d.get("view_box") or ""),
            "has_wheels": bool(d.get("has_wheels")),
            "reason": str(d.get("reason") or r.get("error") or ""),
        }
    return None


@app.get("/r/{job_id}/pelican.svg")
async def result_pelican_svg(job_id: str) -> Response:
    j = await jobs.get(job_id)
    if j is None or j.status != "done" or j.report is None:
        raise HTTPException(status_code=404, detail="result not ready")
    pelican = _pelican_preview(j.report)
    if not pelican or not pelican.get("svg_raw"):
        raise HTTPException(status_code=404, detail="pelican svg unavailable")
    return Response(
        content=pelican["svg_raw"].encode("utf-8"),
        media_type="image/svg+xml; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="clodex-pelican-{job_id}.svg"',
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=86400",
        },
    )


_PROTOCOL_LABELS = {"anthropic": "Claude", "openai": "OpenAI", "gemini": "Gemini"}
_VERDICT_LABELS = {
    "zh": {"passed": "通过", "marginal": "存在风险", "failed": "未达标"},
    "en": {"passed": "passed", "marginal": "risky", "failed": "failed"},
    "ru": {"passed": "пройдено", "marginal": "есть риски", "failed": "не пройдено"},
}


def _seo_meta_for_report(report: dict, locale: str = "ru") -> dict[str, str]:
    """Compute SEO title + description from a finished report.

    Each `/r/{job_id}` is a permanent landing page; embedding domain + model
    + score + verdict makes reports across different models on the same relay
    distinct indexable pages.
    """
    base_url = str(report.get("base_url") or "")
    domain = base_url
    if "://" in base_url:
        domain = base_url.split("://", 1)[1].split("/", 1)[0]
    domain = domain or tr(locale, "relay_fallback")

    protocol = str(report.get("protocol") or "anthropic")
    proto_label = _PROTOCOL_LABELS.get(protocol, protocol)

    model = str(report.get("target_model") or "").strip()
    score = float(report.get("total_score") or 0)
    verdict = str(report.get("verdict") or "failed")
    verdict_label = _VERDICT_LABELS.get(locale, _VERDICT_LABELS["ru"]).get(verdict, verdict)

    results = report.get("results") or []
    pass_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "pass")
    fail_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "fail")
    total = len(results)

    if model:
        title = tr(locale, "seo_report_title_model").format(
            domain=domain, protocol=proto_label, model=model, score=score, verdict=verdict_label
        )
    else:
        title = tr(locale, "seo_report_title").format(
            domain=domain, protocol=proto_label, score=score, verdict=verdict_label
        )
    description = tr(locale, "seo_report_description").format(
        domain=domain,
        protocol=proto_label,
        model=model or "-",
        score=score,
        verdict=verdict_label,
        total=total,
        passed=pass_count,
        failed=fail_count,
    )
    og_description = tr(locale, "seo_report_og").format(
        domain=domain, score=score, verdict=verdict_label, passed=pass_count, total=total
    )
    return {
        "seo_title": title[:155],
        "seo_description": description[:160],
        "seo_og_description": og_description[:155],
    }


@app.get("/r/{job_id}", response_class=HTMLResponse)
async def result_page(request: Request, job_id: str) -> HTMLResponse:
    j = await jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    locale = detect_locale(request)
    if j.status != "done" or j.report is None:
        proto = j.protocol or "anthropic"
        return _render(
            request,
            "running.html",
            job_id=job_id,
            job=j,
            detector_labels=detector_labels_map(locale, proto),
            detector_criteria_map=detector_criteria(locale, proto),
            detector_list=detector_display(locale, proto),
        )
    protocol = str(j.report.get("protocol") or "anthropic")
    if j.report.get("mode") == "pelican":
        tier_title = lt(locale, "Пеликан-тест (SVG)", "Pelican SVG Benchmark", "鹈鹕骑车 SVG 基准测试")
        tier_message = lt(
            locale,
            "Отдельный визуальный бенчмарк Симона Уиллисона (пеликан на велосипеде в SVG) с замером TTFT, реальной скорости потока tok/s и проверкой стриминга.",
            "Standalone Simon Willison visual SVG benchmark (pelican riding a bicycle) measuring TTFT, live streaming tok/s, and true vs. buffered streaming.",
            "独立的 Simon Willison 视觉 SVG 基准测试（鹈鹕骑自行车），同步测量首字延迟 TTFT、真实流式 tok/s 与真/假流式判定。",
        )
    else:
        tier_title, tier_message = tier_banner_for_locale(locale, protocol)
    crit_map = detector_criteria(locale, protocol)
    detector_defs = [
        {"label": label, "criteria": crit_map.get(key, "")}
        for key, label in detector_display(locale, protocol)
    ]
    return _render(
        request,
        "result.html",
        job_id=job_id,
        report=j.report,
        rows=_result_rows_for_locale(j.report, locale),
        report_notes=_report_notes(j.report, locale),
        pelican=_pelican_preview(j.report),
        detector_defs=detector_defs,
        tier_title=tier_title,
        tier_message=tier_message,
        caption=result_caption(
            locale,
            float(j.report.get("total_score") or 0),
            str(j.report.get("verdict") or "failed"),
            protocol,
        ),
        **_seo_meta_for_report(j.report, locale),
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "ts": time.time()})


# SEO + AI GEO surface — see docs/SEO_AI_GEO_PLAN.md §3.1.A/B/C. These three
# files MUST be served at site root (not under /static) for crawlers to find
# them by convention.
@app.get("/robots.txt")
async def robots_txt() -> Response:
    return Response(
        content=(STATIC_DIR / "robots.txt").read_bytes(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/llms.txt")
async def llms_txt() -> Response:
    return Response(
        content=(STATIC_DIR / "llms.txt").read_bytes(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/llms-full.txt")
async def llms_full_txt() -> Response:
    return Response(
        content=(STATIC_DIR / "llms-full.txt").read_bytes(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# (loc, changefreq, priority, template_filename) — lastmod resolved at
# request time from the template file's mtime.
_STATIC_SITEMAP_URLS = [
    ("https://check.clodex.xyz/",            "weekly",  "1.0",  "hub.html"),
    ("https://check.clodex.xyz/claude",      "weekly",  "0.9",  "index.html"),
    ("https://check.clodex.xyz/openai",      "weekly",  "0.9",  "openai.html"),
    ("https://check.clodex.xyz/gemini",      "weekly",  "0.9",  "gemini.html"),
    ("https://check.clodex.xyz/pelican",     "weekly",  "0.9",  "pelican.html"),
    ("https://check.clodex.xyz/compare",     "weekly",  "0.8",  "compare.html"),
    ("https://check.clodex.xyz/faq",         "monthly", "0.8",  "faq.html"),
]

_SITEMAP_REPORT_DIRS = [
    jobs.JOBS_DIR / "anthropic",
    jobs.JOBS_DIR / "openai",
    jobs.JOBS_DIR / "gemini",
    jobs.JOBS_DIR,  # legacy top-level
]


def _template_lastmod(filename: str) -> str:
    """Date string from a template's mtime, or '' if missing/unreadable."""
    try:
        mtime = (TEMPLATE_DIR / filename).stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")


_NON_INDEXABLE_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org", "relay-a.example")


def _is_indexable_report_file(json_path: Path) -> bool:
    """Exclude broken or local/test reports from sitemap.xml."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("run_error"):
        return False
    base_url = str(data.get("base_url") or "").lower()
    if any(h in base_url for h in _NON_INDEXABLE_HOSTS):
        return False
    return True


@app.get("/sitemap.xml")
async def sitemap_xml() -> Response:
    """Dynamic multilingual sitemap — static product pages (with hreflang) + clean public reports."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]

    for loc, freq, prio, tpl in _STATIC_SITEMAP_URLS:
        lastmod = _template_lastmod(tpl)
        lines.append("  <url>")
        lines.append(f"    <loc>{loc}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>{freq}</changefreq>")
        lines.append(f"    <priority>{prio}</priority>")
        lines.append(f'    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>')
        lines.append(f'    <xhtml:link rel="alternate" hreflang="en" href="{loc}?lang=en"/>')
        lines.append(f'    <xhtml:link rel="alternate" hreflang="zh-Hans" href="{loc}?lang=zh"/>')
        lines.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{loc}"/>')
        lines.append("  </url>")

    seen: set[str] = set()
    for dir_path in _SITEMAP_REPORT_DIRS:
        if not dir_path.is_dir():
            continue
        for json_path in sorted(dir_path.glob("*.json")):
            job_id = json_path.stem
            if job_id in seen:
                continue
            seen.add(job_id)
            if not _is_indexable_report_file(json_path):
                continue
            try:
                lastmod = datetime.fromtimestamp(
                    json_path.stat().st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            except OSError:
                continue
            lines.append(
                f"  <url><loc>https://check.clodex.xyz/r/{job_id}</loc>"
                f"<lastmod>{lastmod}</lastmod>"
                f"<changefreq>monthly</changefreq>"
                f"<priority>0.6</priority></url>"
            )

    lines.append("</urlset>\n")
    return Response(
        content="\n".join(lines),
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=600"},
    )


# ----- helpers shared with templates -----


_DETECTOR_DISPLAY = {
    "anthropic": [
        ("identity", "身份一致性"),
        ("behavioral_signature", "行为签名验证"),
        ("thinking_signature", "思维签名验证"),
        ("consistency", "模型一致性"),
        ("knowledge", "知识准确度"),
        ("pdf", "PDF 文档识别"),
        ("structured_output", "结构化输出"),
        ("protocol", "协议规范性"),
        ("integrity", "响应完整性"),
        ("token_usage", "Token 用量"),
        ("message_id", "消息标识规范"),
        ("long_context", "长上下文真实性"),
    ],
    "openai": [
        ("basic_request", "基础请求"),
        ("model_consistency", "模型一致性"),
        ("function_calling", "函数调用"),
        ("structured_output", "结构化输出"),
        ("protocol", "协议规范性"),
        ("integrity", "流式一致性"),
        ("token_billing", "Token 计费"),
        ("long_context", "长上下文真实性"),
    ],
    "gemini": [
        ("basic_request", "基础请求"),
        ("model_info", "模型响应形状"),
        ("function_calling", "函数调用"),
        ("structured_output", "结构化输出"),
        ("protocol", "协议规范性"),
        ("integrity", "流式一致性"),
        ("token_usage", "Token 用量"),
    ],
}


def _result_rows(report: dict) -> list[dict]:
    return _result_rows_for_locale(report, "zh")


def _result_rows_for_locale(report: dict, locale: str) -> list[dict]:
    """Flatten results into the order/labels the result template expects."""
    by_name = {
        r.get("name"): r for r in report.get("results") or []
        if isinstance(r, dict)
    }
    out = []
    protocol = str(report.get("protocol") or "anthropic")
    is_pelican_only = report.get("mode") == "pelican"
    display = detector_display(locale, protocol)
    for name, label in display:
        if is_pelican_only and name not in by_name:
            continue
        r = by_name.get(name) or {"status": "skip", "score": 0.0}
        status = str(r.get("status") or "skip")
        score = float(r.get("score") or 0.0)
        if status == "pass":
            label_short, css = status_short(locale, "pass", name), "ok"
        elif status == "skip" and name == "long_context":
            label_short, css = status_short(locale, "skip", name), "muted"
        elif status == "skip" and name in {"token_billing", "token_usage"}:
            label_short, css = status_short(locale, "skip", name), "muted"
        elif status == "skip":
            label_short, css = status_short(locale, "skip", name), "muted"
        elif status == "error":
            label_short, css = status_short(locale, "error", name), "fail"
        elif score >= 70:
            label_short, css = status_short(locale, "warn", name), "warn"
        else:
            label_short, css = status_short(locale, "fail", name), "fail"
        out.append({
            "name": name,
            "label": label,
            "status": status,
            "label_short": label_short,
            "css": css,
            "score": score,
        })
    return out


def _common_report_notes(report: dict, locale: str = "ru") -> list[dict[str, str]]:
    """Protocol-agnostic diagnostic notes for Prompt Cache, System Injection,
    Tokenizer Probe, and Stream Analysis."""
    results = {
        r.get("name"): r for r in report.get("results") or []
        if isinstance(r, dict)
    }
    notes: list[dict[str, str]] = []

    pc = results.get("prompt_cache") or {}
    if pc and pc.get("status") not in {None, "skip"}:
        pd = pc.get("details") if isinstance(pc.get("details"), dict) else {}
        if pc.get("status") == "pass":
            read_t = pd.get("call2_cache_read") or pd.get("call2_cached_tokens") or pd.get("call1_cached_tokens") or 0
            ratio = pd.get("cache_hit_ratio_pct") or 0
            notes.append({
                "title": lt(locale, "Prompt Caching работает реально", "Prompt Caching verified", "提示词缓存真实生效"),
                "body": lt(
                    locale,
                    f"Повторный запрос с общим префиксом попал в кэш: прочитано {read_t} кэшированных токенов ({ratio}% входа).",
                    f"Back-to-back request hit prefix cache: {read_t} cached tokens read ({ratio}% of input).",
                    f"连续相同前缀请求成功命中缓存：读取 {read_t} 个缓存 token（占输入 {ratio}%）。",
                ),
            })
        elif pc.get("status") == "fail":
            notes.append({
                "title": lt(locale, "Prompt Caching не сработал", "Prompt Caching did not trigger", "提示词缓存未命中"),
                "body": lt(
                    locale,
                    "На двух последовательных запросах с одинаковым префиксом >2000 токенов кэш-хит не зафиксирован (cache_read = 0). Провайдер может отбрасывать cache_control или балансировать запросы между несвязанными аккаунтами.",
                    "Two consecutive calls with an identical >2,000-token prefix recorded 0 cached read tokens. The relay may strip cache_control or route across separate accounts.",
                    "连续两次发送超过 2000 token 的相同前缀未检测到缓存命中 (cache_read = 0)，可能未透传 cache_control 或跨账号轮询导致缓存失效。",
                ),
            })

    si = results.get("system_injection") or {}
    if si and si.get("status") not in {None, "skip", "pass"}:
        sd = si.get("details") if isinstance(si.get("details"), dict) else {}
        bare = sd.get("bare_input_tokens")
        canary_ok = bool(sd.get("canary_followed"))
        if not canary_ok:
            notes.append({
                "title": lt(locale, "Подозрение на перезапись system prompt", "System prompt override suspected", "疑似覆盖或丢弃 system prompt"),
                "body": lt(
                    locale,
                    "Модель не выполнила обязательное правило из вашего system prompt (канареечный тег не появился в ответе). Возможна подмена или удаление системного промпта на стороне релея.",
                    "The model ignored the mandatory rule in your system prompt (canary tag missing). The relay may be stripping or overriding system prompts.",
                    "模型未遵守用户 system prompt 中的强制金丝雀规则，relay 可能剥离或覆盖了系统提示词。",
                ),
            })
        elif isinstance(bare, int) and bare > 45:
            notes.append({
                "title": lt(locale, "Обнаружен скрытый системный промпт в биллинге", "Hidden system-prompt token overhead detected", "检测到隐藏系统提示词注入"),
                "body": lt(
                    locale,
                    f"На минимальный запрос «hi» без system prompt эндпоинт насчитал {bare} входных токенов (норма ≤ 45). Это указывает на скрытую обёртку промпта, за которую платит клиент.",
                    f"A bare 'hi' request with no system prompt reported {bare} input tokens (clean baseline ≤ 45), suggesting a hidden system wrapper billed to the caller.",
                    f"无 system prompt 的纯 'hi' 请求上报了 {bare} 个输入 token（正常 ≤ 45），表明代理可能在后台注入了隐藏提示词并计费。",
                ),
            })

    tp = results.get("tokenizer_probe") or {}
    if tp and tp.get("status") == "fail":
        td = tp.get("details") if isinstance(tp.get("details"), dict) else {}
        notes.append({
            "title": lt(locale, "Аномалия токенизатора", "Tokenizer mismatch detected", "分词器特征异常"),
            "body": lt(
                locale,
                f"Прирост токенов на мультибайтной/пробельной пробе (edge Δ={td.get('edge_delta')}, ws Δ={td.get('ws_delta')}) вышел за ожидаемый диапазон официального токенизатора — возможна подмена модели или неточный подсчёт биллинга.",
                f"Token delta on multibyte/whitespace BPE probes (edge Δ={td.get('edge_delta')}, ws Δ={td.get('ws_delta')}) fell outside the expected official tokenizer band, hinting at model substitution or inaccurate token accounting.",
                f"多字节与空白数字分词探针增量（edge Δ={td.get('edge_delta')}，ws Δ={td.get('ws_delta')}）偏离官方分词器区间，可能存在底层换模或计费偏差。",
            ),
        })

    sa = (report.get("performance") or {}).get("stream_analysis")
    if isinstance(sa, dict) and sa.get("verdict") == "buffered_burst":
        notes.append({
            "title": lt(locale, "Подозрение на буферизованный («фейковый») стрим", "Buffered / non-incremental stream detected", "疑似假流式 / 缓冲整包吐出"),
            "body": lt(
                locale,
                f"Потоковый ответ пришёл почти мгновенным рывком ({sa.get('chunk_count')} чанков за {sa.get('generation_ms')} мс после долгого ожидания первого токена). Вероятно, провайдер буферизует весь ответ целиком вместо настоящего потокового стриминга.",
                f"The streamed response arrived in a single burst ({sa.get('chunk_count')} chunks in {sa.get('generation_ms')}ms after waiting for first token), suggesting the proxy buffers the full response instead of true streaming.",
                f"流式输出在长时间等待首 token 后几乎一次性吐出（{sa.get('chunk_count')} 个分片，耗时 {sa.get('generation_ms')}ms），代理可能缓冲了完整响应而非真流式传输。",
            ),
        })

    vi = results.get("vision_image") or {}
    if vi and vi.get("status") in {"fail", "error"}:
        vd = vi.get("details") if isinstance(vi.get("details"), dict) else {}
        notes.append({
            "title": lt(locale, "Модель не прошла проверку зрения (динамический PNG)", "Dynamic PNG vision check failed", "动态 PNG 图像视觉检测未通过"),
            "body": lt(
                locale,
                f"Эндпоинт не смог прочитать одноразовый код {vd.get('expected_code', 'VRF-XXXX')} со сгенерированного PNG-изображения. Возможна потеря image-блоков на стороне релея или подмена на текстовую модель без мультимодальности.",
                f"The endpoint failed to read the one-time code {vd.get('expected_code', 'VRF-XXXX')} from a dynamically rendered PNG. The relay may strip image inputs or substitute a text-only model.",
                f"接口未能识别动态渲染 PNG 中的随机验证码 {vd.get('expected_code', 'VRF-XXXX')}，代理可能丢弃了图片块或底层替换为不支持视觉的纯文本模型。",
            ),
        })

    dc = results.get("dynamic_challenge") or {}
    if dc and dc.get("status") in {"fail", "error"}:
        notes.append({
            "title": lt(locale, "Сбой в одноразовой анти-кэш задаче", "Dynamic anti-cache challenge failed", "动态防缓存推理未通过"),
            "body": lt(
                locale,
                "Модель ошиблась в простой случайной задаче на арифметику + посимвольный разворот слова в JSON. Это частый признак подмены на слабую модель или некорректной обработки промпта.",
                "The model missed a fresh randomized arithmetic + character-reversal JSON challenge — a common sign of downgrade to a weaker model or prompt corruption.",
                "模型未能完成随机生成的算术与逐字反转 JSON 题目，通常暗示底层被降级为弱模型或请求内容被异常修改。",
            ),
        })

    return notes


def _report_notes(report: dict, locale: str = "ru") -> list[dict[str, str]]:
    """Human-readable localized report notes for the result page."""
    protocol = str(report.get("protocol") or "anthropic")
    if protocol == "gemini":
        return _gemini_report_notes(report, locale) + _common_report_notes(report, locale)
    if protocol == "anthropic":
        return _anthropic_report_notes(report, locale) + _common_report_notes(report, locale)
    if protocol != "openai":
        return _common_report_notes(report, locale)

    results = {
        r.get("name"): r for r in report.get("results") or []
        if isinstance(r, dict)
    }
    notes: list[dict[str, str]] = []

    structured = results.get("structured_output") or {}
    sd = structured.get("details") if isinstance(structured.get("details"), dict) else {}
    if structured and structured.get("status") not in ("pass", "skip"):
        text = str(sd.get("response_text") or "").strip().replace("\n", " ")
        if len(text) > 180:
            text = text[:180] + "..."
        markdown_seen = bool(sd.get("markdown_json_seen"))
        if markdown_seen:
            message = lt(
                locale,
                "Модель обернула JSON в Markdown-блок (```json ... ```), хотя в OpenAI strict-режиме должен возвращаться чистый JSON. Обычно это означает, что параметр response_format дошёл, но на стороне провайдера отвечает не строгий GPT-бэкенд.",
                "The model wrapped JSON in a Markdown code fence (```json ... ```) instead of returning raw JSON under OpenAI strict mode. This typically suggests a non-strict or substituted backend.",
                "底层模型把 JSON 包在 Markdown 代码块里(```json ... ```),OpenAI strict 模式应该返回裸 JSON。说明 response_format 被透传了,但底层模型没有真正理解 strict 模式 — 通常是relay把请求转给了非 GPT 模型。",
            )
        else:
            message = lt(
                locale,
                "Ответ не является валидным JSON. Запрос отправлялся с response_format=json_schema (strict=true), но relay, вероятно, отбросил этот параметр при пересылке.",
                "The response is not valid JSON. The request sent response_format=json_schema (strict=true), so the relay likely stripped this parameter before forwarding.",
                "返回的不是 JSON 也没有代码块包装。请求已发送 response_format=json_schema strict=true,但relay很可能根本没把这个参数透传给后端。",
            )
        if text:
            excerpt_prefix = lt(locale, " Фрагмент ответа: ", " Response excerpt: ", " 实际返回片段: ")
            message += f"{excerpt_prefix}{text}"
        notes.append({
            "title": lt(locale, "Structured Output не сработал", "Structured output did not take effect", "结构化输出没有真正生效"),
            "body": message,
        })

    protocol_result = results.get("protocol") or {}
    pd = (
        protocol_result.get("details")
        if isinstance(protocol_result.get("details"), dict)
        else {}
    )
    issue_codes: set[str] = set()
    for issue in pd.get("issues") or []:
        if isinstance(issue, dict) and isinstance(issue.get("code"), str):
            issue_codes.add(issue["code"])
    impersonation_codes = issue_codes & {
        "usage_contains_claude_fields",
        "usage_contains_gemini_fields",
        "usage_source_non_openai",
    }
    if impersonation_codes:
        notes.append({
            "title": lt(locale, "Подозрение на подмену бэкенда под OpenAI", "Suspected non-OpenAI backend masquerading as OpenAI", "relay疑似伪装成 OpenAI"),
            "body": lt(
                locale,
                "В поле usage обнаружены поля, характерные для Anthropic или Google (например, claude_cache_creation_*, gemini_* или usage_source != openai). Это сильный признак переупаковки ответа от другого провайдера.",
                "The usage object contains Anthropic or Google-specific fields (e.g. claude_cache_creation_*, gemini_*, or a non-openai usage_source). This strongly suggests the relay is translating from another vendor's backend.",
                "响应的 usage 字段里出现了 Anthropic / Google 后端才会用的字段(如 claude_cache_creation_*、gemini_* 或 usage_source 自报非 openai)。这强烈暗示relay把你的请求转发给了别的厂商后端再包装成 OpenAI 响应。",
            ),
        })
    elif "usage_mixed_token_fields" in issue_codes:
        notes.append({
            "title": lt(locale, "Обнаружены следы адаптера в usage", "Adapter layer traces in usage fields", "响应里有适配层痕迹"),
            "body": lt(
                locale,
                "В usage одновременно присутствуют поля Chat Completions (prompt_tokens/completion_tokens) и Responses/Anthropic (input_tokens/output_tokens). Это указывает на слой трансляции, но само по себе не доказывает подмену модели.",
                "The usage object mixes Chat Completions counters (prompt_tokens/completion_tokens) with Responses/Anthropic fields (input_tokens/output_tokens). This indicates a translation layer, though not necessarily model substitution.",
                "返回的 usage 同时含有 OpenAI 的 prompt_tokens/completion_tokens 和 Anthropic/Responses 风格的 input_tokens/output_tokens。通常说明中间有转换层,但还不足以确认换了后端。",
            ),
        })

    token_billing = results.get("token_billing") or {}
    td = (
        token_billing.get("details")
        if isinstance(token_billing.get("details"), dict)
        else {}
    )
    if token_billing:
        if token_billing.get("status") == "skip":
            notes.append({
                "title": lt(locale, "Не удалось проверить корректность биллинга токенов", "Unable to verify token billing accuracy", "暂时无法判断 Token 是否虚报"),
                "body": lt(
                    locale,
                    "Эндпоинт не вернул достаточно полные поля usage, поэтому невозможно достоверно сверить подсчёт токенов.",
                    "The endpoint did not return complete token usage fields, so token counting accuracy could not be verified.",
                    "接口没有给出足够完整的 Token 用量信息,所以这次不能确认它有没有多算。",
                ),
            })
        elif token_billing.get("status") != "pass":
            notes.append({
                "title": lt(locale, "Риск расхождения в учёте токенов", "Token billing discrepancy detected", "Token 计费存在风险"),
                "body": (td.get("evaluation_zh") if locale == "zh" else None) or lt(
                    locale,
                    "Статистика токенов в ответах расходится с ожидаемыми значениями. Рекомендуется перепроверить биллинг у провайдера.",
                    "Reported token counts diverge noticeably from expected values. Double-check provider billing accuracy.",
                    "Token 统计有明显偏差,建议留意是否存在多算或统计错误。",
                ),
            })
    notes.extend(_common_report_notes(report, locale))
    return notes


def _anthropic_report_notes(report: dict, locale: str = "ru") -> list[dict[str, str]]:
    results = {
        r.get("name"): r for r in report.get("results") or []
        if isinstance(r, dict)
    }
    token_usage = results.get("token_usage") or {}
    td = (
        token_usage.get("details")
        if isinstance(token_usage.get("details"), dict)
        else {}
    )
    if not token_usage:
        return []
    if token_usage.get("status") == "skip":
        return [{
            "title": lt(locale, "Не удалось проверить корректность учёта токенов", "Unable to verify token usage", "暂时无法判断 Token 是否虚报"),
            "body": lt(
                locale,
                "Эндпоинт не вернул полные поля usage, поэтому сверка расхода токенов была пропущена.",
                "The endpoint did not return complete usage fields, so token usage verification was skipped.",
                "接口没有返回完整 usage 字段,所以这次不能确认它有没有多算。",
            ),
        }]
    if token_usage.get("status") != "pass":
        return [{
            "title": lt(locale, "Риск расхождения в полях usage", "Token usage discrepancy risk", "Token 用量存在风险"),
            "body": (td.get("evaluation_zh") if locale == "zh" else None) or lt(
                locale,
                "Поля usage отсутствуют или не согласуются между запросами. Не стоит полагаться на эти счётчики для точного биллинга.",
                "Usage fields are incomplete or inconsistent across requests. Avoid relying on these counters for billing reconciliation.",
                "usage 字段缺失或统计不自洽,建议不要直接依赖该relay返回的 token 数做计费核算。",
            ),
        }]
    return []


def _gemini_report_notes(report: dict, locale: str = "ru") -> list[dict[str, str]]:
    results = {
        r.get("name"): r for r in report.get("results") or []
        if isinstance(r, dict)
    }
    notes: list[dict[str, str]] = []

    structured = results.get("structured_output") or {}
    sd = structured.get("details") if isinstance(structured.get("details"), dict) else {}
    if structured and structured.get("status") not in ("pass", "skip"):
        notes.append({
            "title": lt(locale, "Structured Output не сработал", "Structured output did not take effect", "结构化输出没有真正生效"),
            "body": (sd.get("evaluation_zh") if locale == "zh" else None) or lt(
                locale,
                "Запрос отправлялся с OpenAI-совместимым response_format=json_schema (strict=true), но ответ Gemini relay не прошёл валидацию по схеме.",
                "The request sent OpenAI-compatible response_format=json_schema (strict=true), but the Gemini relay output did not parse according to the schema.",
                "请求已发送 OpenAI 兼容的 response_format=json_schema strict=true,但 Gemini relay返回内容无法按 schema 解析。",
            ),
        })

    token_usage = results.get("token_usage") or {}
    td = (
        token_usage.get("details")
        if isinstance(token_usage.get("details"), dict)
        else {}
    )
    if token_usage and token_usage.get("status") != "pass":
        notes.append({
            "title": lt(locale, "Риск расхождения в полях usage", "Token usage discrepancy risk", "Token 用量存在风险"),
            "body": (td.get("evaluation_zh") if locale == "zh" else None) or lt(
                locale,
                "Поля usage неполные или не согласуются между короткими и длинными запросами.",
                "Usage fields are incomplete or inconsistent between short and long prompts.",
                "usage 字段不完整或统计不自洽,建议不要直接依赖它做计费核算。",
            ),
        })

    integrity = results.get("integrity") or {}
    idetails = (
        integrity.get("details")
        if isinstance(integrity.get("details"), dict)
        else {}
    )
    if integrity and integrity.get("status") != "pass":
        notes.append({
            "title": lt(locale, "Расхождение stream и non-stream ответов", "Stream vs non-stream mismatch", "流式响应存在偏差"),
            "body": (idetails.get("evaluation_zh") if locale == "zh" else None) or lt(
                locale,
                "Текст, причина остановки (finish_reason) или usage между stream и non-stream запросами не совпали.",
                "Response text, finish_reason, or usage differed between streaming and non-streaming calls.",
                "stream 与 non-stream 的文本、结束原因或 usage 字段没有对齐。",
            ),
        })

    if not notes and report.get("mode") != "pelican":
        notes.append({
            "title": lt(locale, "Gemini OpenAI-совместимый протокол работает корректно", "Gemini OpenAI-compatible protocol looks healthy", "Gemini OpenAI 兼容协议表现良好"),
            "body": lt(
                locale,
                "Базовый запрос, поля модели, function calling, structured output, стриминг и usage соответствуют спецификации OpenAI Chat Completions.",
                "Basic calls, model metadata, function calling, structured output, streaming, and usage counters conform to the OpenAI Chat Completions spec.",
                "基础请求、模型字段、tool 调用、结构化输出、流式响应和 Token 用量字段基本符合 OpenAI Chat Completions 规范。",
            ),
        })
    return notes

"""Job queue for HTTP-driven detections.

Wraps the same Runner the CLI uses. Single uvicorn worker, in-process state
guarded by an asyncio lock. Done jobs are persisted to disk so a server
restart keeps the shareable result URLs alive. API keys are NEVER persisted —
the masked form goes to disk; the raw key lives only in the Job until the run
finishes, then is dropped from memory.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from relay_detector.models import (
    DetectionReport,
    DetectionTier,
    ExecutionConfig,
    Mode,
    Protocol,
    mask_api_key,
)
from relay_detector.core.stream_metrics import summarize_stream_samples
from relay_detector.scorer import (
    compute_total,
    effective_verdict,
    fatal_run_error,
    summary_text,
)


JobStatus = Literal["queued", "running", "done", "error"]

# Production default; override via CLODEX_CHECK_JOBS_DIR in tests / dev so the
# import doesn't try to mkdir into /opt/clodex-check on a developer laptop.
JOBS_DIR = Path(
    os.environ.get("CLODEX_CHECK_JOBS_DIR", "/opt/clodex-check/web_data/jobs")
)
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Cap concurrent detections so a flood of submissions doesn't exhaust file
# descriptors or get the upstream Anthropic API rate-limited. Each detection
# already runs ~13 outbound requests in parallel, so 6 inflight = ~78 sockets.
_MAX_INFLIGHT = 6
_SEMA = asyncio.Semaphore(_MAX_INFLIGHT)


@dataclass
class Job:
    id: str
    protocol: str = "anthropic"
    status: JobStatus = "queued"
    base_url: str = ""
    target_model: str = ""
    mode: str = "full"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    report: dict[str, Any] | None = None
    error: str | None = None
    detector_order: list[str] = field(default_factory=list)
    detectors: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


def _summarize_detector_result(
    name: str,
    status: str,
    details: dict[str, Any] | None,
    error: str | None,
) -> str:
    if error:
        cleaned = " ".join(str(error).split())
        return cleaned[:140] + ("…" if len(cleaned) > 140 else "")
    d = details if isinstance(details, dict) else {}
    if status == "skip":
        reason = d.get("skip_reason") or d.get("reason")
        if isinstance(reason, str) and reason:
            return reason[:100]
        return "skipped"
    if name == "thinking_signature":
        sig_len = d.get("signature_length")
        t_chars = d.get("thinking_text_chars")
        if sig_len:
            extra = f", thinking {t_chars} ch" if t_chars else ""
            return f"signature {sig_len} B{extra}"
        ev = d.get("evaluation")
        if ev:
            return str(ev)
    elif name == "behavioral_signature":
        hits, total = d.get("hits"), d.get("total")
        if hits is not None and total:
            return f"{hits}/{total} signatures"
    elif name == "identity":
        req = d.get("required_hits") or []
        brands = d.get("detected_non_anthropic_brands") or []
        if brands:
            return "brands: " + ", ".join(str(b) for b in brands[:3])
        return f"signals {len(req)}/2"
    elif name in {"consistency", "model_consistency"}:
        parts: list[str] = []
        if d.get("model_match") is True:
            parts.append("model OK")
        elif d.get("model_match") is False:
            parts.append(f"model={d.get('response_model') or '?'}")
        if d.get("stability_cv") is not None:
            parts.append(f"CV={d['stability_cv']}")
        if parts:
            return ", ".join(parts)
    elif name == "knowledge":
        passes, total = d.get("passes"), d.get("total")
        if passes is not None and total:
            return f"{passes}/{total} answers"
    elif name == "pdf":
        ev = d.get("evaluation")
        if ev == "magic_found":
            return "MAGIC token verified"
        if ev:
            return str(ev)
    elif name in {"structured_output", "function_calling"}:
        sub = d.get("sub_checks")
        if isinstance(sub, dict) and sub:
            ok = sum(1 for v in sub.values() if isinstance(v, dict) and v.get("pass"))
            return f"{ok}/{len(sub)} checks OK"
    elif name == "integrity":
        sub = d.get("sub_checks")
        if isinstance(sub, dict) and sub:
            parts = []
            sim = sub.get("similarity")
            if isinstance(sim, dict) and sim.get("ratio") is not None:
                parts.append(f"sim {sim['ratio']}%")
            inp = sub.get("input_tokens")
            if isinstance(inp, dict) and inp.get("ns") is not None and inp.get("stream") is not None:
                parts.append(f"in {inp['ns']}/{inp['stream']}")
            if parts:
                return ", ".join(parts)
    elif name in {"token_usage", "token_billing"}:
        sub = d.get("sub_checks")
        if isinstance(sub, dict) and sub:
            ok = sum(1 for v in sub.values() if isinstance(v, dict) and v.get("pass"))
            return f"{ok}/{len(sub)} sub-checks OK"
    elif name == "protocol":
        obs = d.get("observation_count")
        issues = d.get("issue_count")
        if obs is not None and issues is not None:
            return f"{obs} responses, {issues} issues"
    elif name == "message_id":
        obs = d.get("observation_count")
        viols = d.get("violations")
        if obs is not None:
            v_cnt = len(viols) if isinstance(viols, list) else 0
            return f"{obs} IDs, {v_cnt} issues"
    elif name == "basic_request":
        if d.get("finish_reason"):
            return f"finish_reason={d['finish_reason']}"
    elif name == "pelican_svg":
        if d.get("valid_svg"):
            return (
                f"{d.get('primitive_count', 0)} shapes, "
                f"{d.get('unique_colors', 0)} colors, "
                f"{d.get('svg_bytes', 0)} B"
            )
        if d.get("reason"):
            return str(d["reason"])[:100]
    elif name == "prompt_cache":
        if d.get("cache_read_hit"):
            ratio = d.get("cache_hit_ratio_pct")
            read_t = d.get("call2_cache_read") or d.get("call2_cached_tokens") or d.get("call1_cached_tokens") or 0
            return f"cache HIT {read_t} tok ({ratio}%)"
        w_t = d.get("call1_cache_creation") or 0
        if w_t > 0:
            return f"write {w_t} tok, read 0"
        return "no cache hit"
    elif name == "system_injection":
        canary = "canary OK" if d.get("canary_followed") else "canary MISSED"
        bare = d.get("bare_input_tokens")
        return f"{canary}, bare={bare} tok ({d.get('overhead_label', '?')})"
    elif name == "tokenizer_probe":
        return f"edge Δ={d.get('edge_delta')}, ws Δ={d.get('ws_delta')}"
    elif name == "vision_image":
        verdict = d.get("verdict")
        if verdict == "exact_match":
            return f"OCR exact ({d.get('expected_code', '')})"
        if verdict == "digits_matched":
            return f"digits matched ({d.get('expected_code', '')})"
        return f"missed ({d.get('expected_code', '?')})"
    elif name == "dynamic_challenge":
        c_ok = "calc OK" if d.get("calc_ok") else "calc FAIL"
        r_ok = "rev OK" if d.get("rev_ok") else "rev FAIL"
        return f"{c_ok}, {r_ok}"
    return ""


_JOBS: dict[str, Job] = {}
_LOCK = asyncio.Lock()
_CURRENT_ON_EVENT: contextvars.ContextVar[Callable[[dict[str, Any]], None] | None] = (
    contextvars.ContextVar("clodex_check_on_event", default=None)
)


def _new_job_id() -> str:
    # 8-char URL-safe id; secrets gives ~48 bits of entropy, fine for an
    # unguessable shareable link without auth.
    return secrets.token_urlsafe(6)


async def submit(
    base_url: str,
    api_key: str,
    model: str,
    mode: str,
    protocol: str = "anthropic",
    include_long_context: bool = False,
    include_long_context_extreme: bool = False,
) -> str:
    """Queue a detection job and return the job id immediately.

    Long-context probe is opt-in. Two tiers:
      - ``include_long_context`` (standard): 32k/100k/200k probes,
        $0.05–$0.50 upstream cost, 30–90s extra wall time.
      - ``include_long_context_extreme`` (adaptive): probes proportionally
        up to the model's advertised limit (e.g. 32k→500k→950k for 1M
        models). $0.05–$8 cost, 30s–5min wall time. Catches "advertised X
        but capped at Y<X" fraud that the standard tier misses on big
        models. Implies standard (it's a superset).
    """
    job_id = _new_job_id()
    job = Job(
        id=job_id,
        protocol=protocol,
        base_url=base_url,
        target_model=model,
        mode=mode,
    )
    async with _LOCK:
        _JOBS[job_id] = job
    asyncio.create_task(
        _run(
            job_id, base_url, api_key, model, mode, protocol,
            include_long_context, include_long_context_extreme,
        )
    )
    return job_id


async def get(job_id: str) -> Job | None:
    """Look up a job by id. Falls back to disk for jobs that survived a restart."""
    async with _LOCK:
        j = _JOBS.get(job_id)
    if j is not None:
        return j
    report = None
    for path in _report_candidates(job_id):
        if not path.exists():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            break
        except (json.JSONDecodeError, OSError):
            continue
    if report is None:
        return None
    return Job(
        id=job_id,
        status="done",
        protocol=report.get("protocol", "anthropic"),
        base_url=report.get("base_url", ""),
        target_model=report.get("target_model", ""),
        mode=report.get("mode", "full"),
        created_at=time.time(),
        finished_at=time.time(),
        report=report,
    )


def report_path(job_id: str, protocol: str) -> Path:
    protocol_dir = JOBS_DIR / protocol
    protocol_dir.mkdir(parents=True, exist_ok=True)
    return protocol_dir / f"{job_id}.json"


def image_path(job_id: str, protocol: str) -> Path:
    protocol_dir = JOBS_DIR / protocol
    protocol_dir.mkdir(parents=True, exist_ok=True)
    return protocol_dir / f"{job_id}.jpg"


def _report_candidates(job_id: str) -> list[Path]:
    return [
        JOBS_DIR / f"{job_id}.json",
        JOBS_DIR / "anthropic" / f"{job_id}.json",
        JOBS_DIR / "openai" / f"{job_id}.json",
        JOBS_DIR / "gemini" / f"{job_id}.json",
    ]


async def _run(
    job_id: str,
    base_url: str,
    api_key: str,
    model: str,
    mode: str,
    protocol: str,
    include_long_context: bool = False,
    include_long_context_extreme: bool = False,
) -> None:
    async with _SEMA:
        async with _LOCK:
            j = _JOBS.get(job_id)
            if j is None:
                return
            j.status = "running"
            j.started_at = time.time()
            j.events.append(
                {
                    "ts_ms": 0,
                    "type": "run_start",
                    "model": model,
                    "mode": mode,
                }
            )

        run_started_wall = j.started_at or time.time()

        def _record_event(ev: dict[str, Any]) -> None:
            job_obj = _JOBS.get(job_id)
            if job_obj is None:
                return
            ts_ms = max(0, int((time.time() - run_started_wall) * 1000))
            etype = ev.get("type")
            if etype == "plan":
                order: list[str] = []
                for item in ev.get("detectors") or []:
                    dname = item.get("name")
                    if not dname:
                        continue
                    order.append(dname)
                    job_obj.detectors[dname] = {
                        "name": dname,
                        "kind": item.get("kind", "active"),
                        "weight": item.get("weight", 0.0),
                        "status": item.get("status", "queued"),
                        "score": None,
                        "duration_ms": None,
                        "summary": item.get("reason") or "",
                        "error": None,
                    }
                job_obj.detector_order = order
                active_cnt = sum(
                    1 for d in job_obj.detectors.values() if d.get("kind") != "skip"
                )
                job_obj.events.append(
                    {
                        "ts_ms": ts_ms,
                        "type": "plan",
                        "active_count": active_cnt,
                        "total_count": len(order),
                    }
                )
            elif etype == "detector_start":
                dname = ev.get("name")
                if dname:
                    cur = job_obj.detectors.setdefault(
                        dname,
                        {
                            "name": dname,
                            "kind": "active",
                            "weight": ev.get("weight", 0.0),
                        },
                    )
                    cur["status"] = "running"
                    job_obj.events.append(
                        {"ts_ms": ts_ms, "type": "detector_start", "name": dname}
                    )
            elif etype == "detector_done":
                dname = ev.get("name")
                if dname:
                    status = ev.get("status", "error")
                    score = ev.get("score")
                    dur = ev.get("duration_ms")
                    err_txt = ev.get("error")
                    summary = _summarize_detector_result(
                        dname, status, ev.get("details"), err_txt
                    )
                    cur = job_obj.detectors.setdefault(
                        dname,
                        {
                            "name": dname,
                            "kind": "active",
                            "weight": ev.get("weight", 0.0),
                        },
                    )
                    cur["status"] = status
                    cur["score"] = score
                    cur["duration_ms"] = dur
                    cur["summary"] = summary
                    cur["error"] = (str(err_txt)[:160] if err_txt else None)
                    job_obj.events.append(
                        {
                            "ts_ms": ts_ms,
                            "type": "detector_done",
                            "name": dname,
                            "status": status,
                            "score": score,
                            "duration_ms": dur,
                            "summary": summary,
                        }
                    )
            elif etype == "ttft_probe_start":
                job_obj.events.append({"ts_ms": ts_ms, "type": "ttft_probe_start"})
            elif etype == "run_complete":
                job_obj.events.append(
                    {
                        "ts_ms": ts_ms,
                        "type": "run_complete",
                        "total_latency_ms": ev.get("total_latency_ms"),
                        "request_count": ev.get("request_count"),
                    }
                )

        try:
            cfg = ExecutionConfig.for_mode(
                Mode(mode), max_concurrent=3, request_timeout_s=45.0
            )
            cfg.include_long_context = include_long_context
            cfg.include_long_context_extreme = include_long_context_extreme
            # Long-context probes blow past the regular per-mode wall-clock
            # budget (60–180s). 1M-token requests alone take 2–4 minutes
            # upstream; the extreme path may also sleep 75s per tier waiting
            # for an OpenAI/Anthropic TPM window to reset before retrying
            # rate-limited probes (see _probe_tier_with_tpm_retry).
            # Without this bump asyncio.wait_for kills the runner
            # mid-detector and the user gets a misleading "fail" instead.
            if include_long_context_extreme:
                cfg.overall_timeout_s = max(cfg.overall_timeout_s, 900.0)
            elif include_long_context:
                cfg.overall_timeout_s = max(cfg.overall_timeout_s, 300.0)
            ev_token = _CURRENT_ON_EVENT.set(_record_event)
            try:
                if protocol == "openai":
                    outcome = await _run_openai(base_url, api_key, model, cfg)
                    report_protocol = Protocol.OPENAI
                    report_tier = DetectionTier.BEHAVIORAL
                    tier_title = "行为/协议级验证"
                    tier_message = (
                        "本检测无法可靠区分高配模型真品与低配模型伪装。"
                        "我们检测的是relay接口是否符合 OpenAI Chat Completions 协议规范、"
                        "能力是否完整、usage 字段是否符合官方响应形状。"
                    )
                elif protocol == "gemini":
                    outcome = await _run_gemini(base_url, api_key, model, cfg)
                    report_protocol = Protocol.GEMINI
                    report_tier = DetectionTier.PROTOCOL
                    tier_title = "协议级验证"
                    tier_message = (
                        "本检测通过 OpenAI 兼容协议 (POST /chat/completions) 探测 Gemini relay,"
                        "验证响应字段、tool 调用、结构化输出、流式一致性和 usage 字段是否符合 OpenAI 规范。"
                        "它不提供加密级模型真伪证明。"
                    )
                elif protocol == "anthropic":
                    outcome = await _run_anthropic(base_url, api_key, model, cfg)
                    report_protocol = Protocol.ANTHROPIC
                    report_tier = DetectionTier.CRYPTOGRAPHIC
                    tier_title = "加密级验证"
                    tier_message = (
                        "Claude thinking signature 来自 Anthropic 服务端签名。"
                        "通过该项时,它是当前检测集中最高可信度的真伪信号。"
                    )
                else:
                    raise ValueError(f"unsupported protocol: {protocol}")
            finally:
                _CURRENT_ON_EVENT.reset(ev_token)

            run_error = fatal_run_error(outcome.results)
            score = 0.0 if run_error else compute_total(outcome.results)
            verdict = effective_verdict(score, outcome.results)
            summary = run_error or summary_text(score, verdict)

            self_id: str | None = None
            brands: list[str] = []
            for r in outcome.results:
                if r.name != "identity" or not isinstance(r.details, dict):
                    continue
                text = r.details.get("response_text")
                if isinstance(text, str) and text.strip():
                    self_id = text.strip()
                b = r.details.get("detected_non_anthropic_brands")
                if isinstance(b, list):
                    brands = [x for x in b if isinstance(x, str)]
                break

            report = DetectionReport(
                protocol=report_protocol,
                tier=report_tier,
                tier_title=tier_title,
                tier_message=tier_message,
                base_url=base_url,
                api_key_masked=mask_api_key(api_key),
                target_model=model,
                mode=Mode(mode),
                timestamp=datetime.now(timezone.utc),
                total_score=score,
                verdict=verdict,
                results=outcome.results,
                performance=outcome.performance,
                summary=summary,
                run_error=run_error,
                self_reported_identity=self_id,
                detected_non_anthropic_brands=brands,
            )
            report_dict = json.loads(report.model_dump_json())
            report_path(job_id, protocol).write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            async with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id].status = "done"
                    _JOBS[job_id].protocol = protocol
                    _JOBS[job_id].report = report_dict
                    _JOBS[job_id].finished_at = time.time()

        except Exception as e:  # noqa: BLE001 — bubble error into job state
            async with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id].status = "error"
                    _JOBS[job_id].error = f"{type(e).__name__}: {e}"
                    _JOBS[job_id].finished_at = time.time()


async def _run_anthropic(
    base_url: str,
    api_key: str,
    model: str,
    cfg: ExecutionConfig,
):
    from relay_detector.protocols.anthropic import (
        build_detectors,
        build_runner,
        make_client,
    )

    async with make_client(base_url, api_key, timeout=cfg.request_timeout_s) as client:
        runner = build_runner(client, build_detectors(cfg.mode), cfg)
        return await runner.run(model, on_event=_CURRENT_ON_EVENT.get())


async def _run_openai(
    base_url: str,
    api_key: str,
    model: str,
    cfg: ExecutionConfig,
):
    from relay_detector.protocols.openai import (
        build_detectors,
        build_runner,
        make_client,
    )

    async with make_client(base_url, api_key, timeout=cfg.request_timeout_s) as client:
        runner = build_runner(client, build_detectors(cfg.mode), cfg)
        return await runner.run(model, on_event=_CURRENT_ON_EVENT.get())


async def _run_gemini(
    base_url: str,
    api_key: str,
    model: str,
    cfg: ExecutionConfig,
):
    from relay_detector.protocols.gemini import (
        build_detectors,
        build_runner,
        make_client,
    )

    async with make_client(base_url, api_key, timeout=cfg.request_timeout_s) as client:
        runner = build_runner(client, build_detectors(cfg.mode), cfg)
        return await runner.run(model, on_event=_CURRENT_ON_EVENT.get())


async def _execute_pelican_detector(
    base_url: str,
    api_key: str,
    model: str,
    protocol: str,
    reasoning_effort: str | None = None,
    timeout_s: float = 300.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run ONLY the streamed PelicanSVGDetector and capture live stream metrics."""
    started = time.perf_counter()
    if protocol == "openai":
        from relay_detector.protocols.openai import make_client
        from relay_detector.protocols.openai.client import ThrottledOpenAIClient
        from relay_detector.protocols.openai.detectors.pelican_svg import PelicanSVGDetector

        async with make_client(base_url, api_key, timeout=timeout_s) as base_client:
            client = ThrottledOpenAIClient(base_client, max_concurrent=1)
            res = await PelicanSVGDetector(reasoning_effort=reasoning_effort).run(client, model)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            ttft_ms = min(client._ttft_samples_ms) if client._ttft_samples_ms else None
            tps, stream_analysis = summarize_stream_samples(client._stream_samples)
            usage = client.total_usage.model_dump()
    elif protocol == "gemini":
        from relay_detector.protocols.gemini import make_client
        from relay_detector.protocols.gemini.client import ThrottledGeminiClient
        from relay_detector.protocols.gemini.detectors.pelican_svg import PelicanSVGDetector

        async with make_client(base_url, api_key, timeout=timeout_s) as base_client:
            client = ThrottledGeminiClient(base_client, max_concurrent=1)
            res = await PelicanSVGDetector(reasoning_effort=reasoning_effort).run(client, model)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            ttft_ms = min(client._ttft_samples_ms) if client._ttft_samples_ms else None
            tps, stream_analysis = summarize_stream_samples(client._stream_samples)
            usage = client.total_usage.model_dump()
    else:
        from relay_detector.protocols.anthropic import make_client
        from relay_detector.protocols.anthropic.client import ThrottledClient
        from relay_detector.protocols.anthropic.detectors.pelican_svg import PelicanSVGDetector

        async with make_client(base_url, api_key, timeout=timeout_s) as base_client:
            client = ThrottledClient(base_client, max_concurrent=1)
            res = await PelicanSVGDetector(reasoning_effort=reasoning_effort).run(client, model)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            ttft_ms = min(client._ttft_samples_ms) if client._ttft_samples_ms else None
            tps, stream_analysis = summarize_stream_samples(client._stream_samples)
            usage = client.total_usage.model_dump()

    res.duration_ms = elapsed_ms
    perf = {
        "total_latency_ms": elapsed_ms,
        "ttft_ms": ttft_ms,
        "tokens_per_second": tps,
        "stream_analysis": stream_analysis,
        "request_count": 1,
        "backoff_events": 0,
        "usage": usage,
    }
    return json.loads(res.model_dump_json()), perf


def _build_pelican_report(
    proto: str,
    base_url: str,
    api_key: str,
    model: str,
    result_dict: dict[str, Any],
    perf: dict[str, Any],
) -> dict[str, Any]:
    score = float(result_dict.get("score") or 0.0)
    status = str(result_dict.get("status") or "fail")
    if status == "pass":
        verdict = "passed"
    elif score >= 60.0:
        verdict = "marginal"
    else:
        verdict = "failed"

    return {
        "protocol": proto,
        "tier": "visual",
        "tier_title": "Пеликан-тест (SVG)",
        "tier_message": (
            "Отдельный визуальный бенчмарк Симона Уиллисона (пеликан на велосипеде в SVG) "
            "с замером TTFT, реальной скорости потока tok/s и проверкой стриминга."
        ),
        "base_url": base_url,
        "api_key_masked": mask_api_key(api_key),
        "target_model": model,
        "mode": "pelican",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_score": score,
        "verdict": verdict,
        "results": [result_dict],
        "performance": perf,
        "summary": result_dict.get("error") or f"Pelican SVG score: {score:.0f}/100",
        "run_error": result_dict.get("error") if status == "error" else None,
        "self_reported_identity": None,
        "detected_non_anthropic_brands": [],
    }


async def run_pelican(
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "anthropic",
    reasoning_effort: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run a standalone Pelican-on-a-bicycle SVG check and persist a shareable report.

    API keys are NEVER written to disk or returned in the report payload.
    """
    proto = protocol if protocol in {"anthropic", "openai", "gemini"} else "anthropic"
    async with _SEMA:
        result_dict, perf = await _execute_pelican_detector(
            base_url,
            api_key,
            model,
            proto,
            reasoning_effort=reasoning_effort,
        )

    job_id = _new_job_id()
    report_dict = _build_pelican_report(proto, base_url, api_key, model, result_dict, perf)
    report_path(job_id, proto).write_text(
        json.dumps(report_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    now = time.time()
    async with _LOCK:
        _JOBS[job_id] = Job(
            id=job_id,
            protocol=proto,
            status="done",
            base_url=base_url,
            target_model=model,
            mode="pelican",
            created_at=now,
            started_at=now,
            finished_at=now,
            report=report_dict,
        )
    return job_id, report_dict


async def submit_pelican(
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "anthropic",
    reasoning_effort: str | None = None,
) -> str:
    """Queue an async Pelican SVG job so long high-reasoning runs never hit
    reverse-proxy 504 timeouts."""
    proto = protocol if protocol in {"anthropic", "openai", "gemini"} else "anthropic"
    job_id = _new_job_id()
    job = Job(
        id=job_id,
        protocol=proto,
        status="queued",
        base_url=base_url,
        target_model=model,
        mode="pelican",
        detector_order=["pelican_svg"],
    )
    async with _LOCK:
        _JOBS[job_id] = job
    asyncio.create_task(
        _run_pelican_job(job_id, base_url, api_key, model, proto, reasoning_effort)
    )
    return job_id


async def _run_pelican_job(
    job_id: str,
    base_url: str,
    api_key: str,
    model: str,
    proto: str,
    reasoning_effort: str | None,
) -> None:
    async with _SEMA:
        async with _LOCK:
            if job_id in _JOBS:
                _JOBS[job_id].status = "running"
                _JOBS[job_id].started_at = time.time()
        try:
            result_dict, perf = await _execute_pelican_detector(
                base_url,
                api_key,
                model,
                proto,
                reasoning_effort=reasoning_effort,
            )
            report_dict = _build_pelican_report(proto, base_url, api_key, model, result_dict, perf)
            report_path(job_id, proto).write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            async with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id].status = "done"
                    _JOBS[job_id].report = report_dict
                    _JOBS[job_id].finished_at = time.time()
        except Exception as e:  # noqa: BLE001
            async with _LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id].status = "error"
                    _JOBS[job_id].error = f"{type(e).__name__}: {e}"
                    _JOBS[job_id].finished_at = time.time()

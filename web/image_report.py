"""Render a detection report as a downloadable CLODEX-branded JPG.

Layout mirrors the result page: circular score badge on the left, per-detector
pass/fail rows on the right, and five metric tiles along the bottom. Drawn with
Pillow primitives — no headless browser dependency.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .i18n import detector_display, lt, normalize_locale, result_caption, status_short


_FONT_CANDIDATES_CYRILLIC_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_CANDIDATES_CYRILLIC_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_CANDIDATES_CJK_REGULAR = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_CANDIDATES_CJK_BOLD = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(
    size: int,
    bold: bool = False,
    locale: str = "ru",
) -> ImageFont.FreeTypeFont:
    loc = normalize_locale(locale)
    if loc == "zh":
        candidates = _FONT_CANDIDATES_CJK_BOLD if bold else _FONT_CANDIDATES_CJK_REGULAR
    else:
        candidates = (
            _FONT_CANDIDATES_CYRILLIC_BOLD if bold else _FONT_CANDIDATES_CYRILLIC_REGULAR
        )
    for p in candidates:
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# CLODEX dark obsidian + emerald palette
_ACCENT = (57, 255, 136)
_ACCENT_SOFT = (18, 41, 28)
_SUCCESS = (57, 255, 136)
_SUCCESS_MID = (34, 197, 94)
_WARN = (245, 158, 11)
_DANGER = (239, 68, 68)
_TEXT = (242, 247, 243)
_MUTED = (165, 177, 169)
_LINE = (29, 41, 34)
_BG = (8, 11, 9)
_TILE_BG = (13, 18, 15)
_CHECK_INK = (7, 21, 13)


def _status_color(status: str, score: float) -> tuple[int, int, int]:
    if status == "pass":
        return _SUCCESS
    if status == "skip":
        return _MUTED
    if status == "error":
        return _DANGER
    if score >= 70:
        return _WARN
    return _DANGER


def _verdict_color(score: float, verdict: str) -> tuple[int, int, int]:
    if verdict == "passed" and score >= 85:
        return _SUCCESS
    if verdict == "passed":
        return _SUCCESS_MID
    if verdict == "marginal":
        return _WARN
    return _DANGER


def _draw_check(
    d: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    color: tuple[int, int, int],
) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    p1 = (cx - r * 0.45, cy + r * 0.05)
    p2 = (cx - r * 0.10, cy + r * 0.40)
    p3 = (cx + r * 0.50, cy - r * 0.30)
    d.line([p1, p2, p3], fill=_CHECK_INK, width=max(2, r // 6))


def _draw_cross(
    d: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    color: tuple[int, int, int],
) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    pad = r * 0.45
    d.line(
        [(cx - pad, cy - pad), (cx + pad, cy + pad)],
        fill=(255, 255, 255),
        width=max(2, r // 6),
    )
    d.line(
        [(cx - pad, cy + pad), (cx + pad, cy - pad)],
        fill=(255, 255, 255),
        width=max(2, r // 6),
    )


def _draw_circle_score(
    d: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int,
    score: float,
    caption: str,
    ring_color: tuple[int, int, int],
    locale: str,
) -> None:
    ring_thickness = 14
    d.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=ring_color,
    )
    inner_r = radius - ring_thickness
    d.ellipse(
        (cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
        fill=_BG,
    )

    score_text = f"{int(round(score))}%"
    score_font = _load_font(72, bold=True, locale=locale)
    bbox = d.textbbox((0, 0), score_text, font=score_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        (cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1] - 16),
        score_text,
        fill=_TEXT,
        font=score_font,
    )

    caption_font = _load_font(18, bold=False, locale=locale)
    cb = d.textbbox((0, 0), caption, font=caption_font)
    cw = cb[2] - cb[0]
    d.text(
        (cx - cw / 2 - cb[0], cy + 32),
        caption,
        fill=_MUTED,
        font=caption_font,
    )


def _draw_metric_tile(
    d: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    label: str,
    value: str,
    locale: str,
    highlight: bool = False,
) -> None:
    border = _DANGER if highlight else _LINE
    d.rounded_rectangle(
        (x, y, x + w, y + h),
        radius=12,
        fill=_TILE_BG,
        outline=border,
        width=2 if highlight else 1,
    )
    label_font = _load_font(13, bold=False, locale=locale)
    value_font = _load_font(24, bold=True, locale=locale)

    lb = d.textbbox((0, 0), label, font=label_font)
    lw = lb[2] - lb[0]
    d.text(
        (x + w / 2 - lw / 2 - lb[0], y + 18 - lb[1]),
        label,
        fill=_MUTED,
        font=label_font,
    )

    vb = d.textbbox((0, 0), value, font=value_font)
    vw, vh = vb[2] - vb[0], vb[3] - vb[1]
    d.text(
        (x + w / 2 - vw / 2 - vb[0], y + h - 24 - vh - vb[1]),
        value,
        fill=_TEXT,
        font=value_font,
    )


def _format_count(n: int | float | None) -> str:
    if n is None:
        return "—"
    if isinstance(n, float):
        return f"{n:,.1f}"
    return f"{n:,}"


def _tokens_per_second(report: dict[str, Any]) -> float | None:
    perf = report.get("performance") or {}
    stream_tps = perf.get("tokens_per_second")
    if isinstance(stream_tps, (int, float)) and stream_tps > 0:
        return round(float(stream_tps), 1)
    out = (perf.get("usage") or {}).get("output_tokens")
    latency_ms = perf.get("total_latency_ms")
    if not out or not latency_ms:
        return None
    return round(out * 1000.0 / latency_ms, 1)


def _jpg_note(report: dict[str, Any], locale: str) -> str:
    protocol = str(report.get("protocol") or "anthropic")
    results = {
        r.get("name"): r for r in report.get("results", [])
        if isinstance(r, dict)
    }
    if protocol == "openai":
        structured = results.get("structured_output") or {}
        if structured.get("status") != "pass":
            return lt(
                locale,
                "Structured Output не прошёл валидацию JSON Schema.",
                "Structured output failed strict JSON Schema validation.",
                "结构化输出未通过 JSON Schema 校验。",
            )
        token_billing = results.get("token_billing") or {}
        if token_billing.get("status") == "fail":
            return lt(
                locale,
                "Обнаружено расхождение в подсчёте токенов.",
                "Token billing discrepancy detected.",
                "Token 计费存在明显偏差。",
            )
    elif protocol == "anthropic":
        token_usage = results.get("token_usage") or {}
        if token_usage.get("status") == "fail":
            return lt(
                locale,
                "Поля usage неполные или расходятся между запросами.",
                "Usage fields are incomplete or inconsistent.",
                "Token 用量字段缺失或统计偏差明显。",
            )
    elif protocol == "gemini":
        structured = results.get("structured_output") or {}
        if structured.get("status") != "pass":
            return lt(
                locale,
                "Structured Output не прошёл валидацию JSON Schema.",
                "Structured output failed JSON Schema validation.",
                "结构化输出未通过 JSON Schema 校验。",
            )
    return ""


def render_report_jpg(report: dict[str, Any], locale: str = "ru") -> bytes:
    """Render the report into a CLODEX-branded JPG and return bytes."""
    loc = normalize_locale(locale)
    W, H = 1400, 1000
    img = Image.new("RGB", (W, H), _BG)
    d = ImageDraw.Draw(img)

    # Top indigo accent bar
    d.rectangle((0, 0, W, 6), fill=_ACCENT)

    # ------- header -------
    title_font = _load_font(32, bold=True, locale=loc)
    protocol = str(report.get("protocol") or "anthropic")
    if protocol == "openai":
        title = lt(loc, "Отчёт проверки OpenAI API", "OpenAI API Check Report", "OpenAI relay 检测报告")
    elif protocol == "gemini":
        title = lt(loc, "Отчёт проверки Gemini API", "Gemini API Check Report", "Gemini relay 检测报告")
    else:
        title = lt(loc, "Отчёт проверки Claude API", "Claude API Check Report", "Claude relay 检测报告")
    d.text((60, 48), title, fill=_TEXT, font=title_font)

    # brand pill in top-right
    pill_font = _load_font(17, bold=True, locale=loc)
    pill_text = "check.clodex.xyz"
    pb = d.textbbox((0, 0), pill_text, font=pill_font)
    pw = pb[2] - pb[0]
    pill_x = W - 60 - pw - 36
    pill_y = 54
    d.rounded_rectangle(
        (pill_x, pill_y - 8, pill_x + pw + 36, pill_y + 30),
        radius=19,
        fill=_ACCENT_SOFT,
        outline=_ACCENT,
        width=1,
    )
    d.text(
        (pill_x + 18 - pb[0], pill_y - pb[1] + 1),
        pill_text,
        fill=_ACCENT,
        font=pill_font,
    )

    d.line([(60, 110), (W - 60, 110)], fill=_LINE, width=1)

    # ------- left: score circle -------
    score = float(report.get("total_score", 0.0))
    verdict = str(report.get("verdict") or "failed")
    ring = _verdict_color(score, verdict)
    caption = result_caption(loc, score, verdict, protocol)

    circle_cx, circle_cy = 290, 405
    circle_r = 170
    _draw_circle_score(d, circle_cx, circle_cy, circle_r, score, caption, ring, loc)

    sub_font = _load_font(16, bold=False, locale=loc)
    model_label = str(report.get("target_model") or "")
    mode_label = str(report.get("mode") or "")
    sub_text = f"{model_label}  ·  {mode_label}" if model_label else mode_label
    sb = d.textbbox((0, 0), sub_text, font=sub_font)
    sw = sb[2] - sb[0]
    d.text(
        (circle_cx - sw / 2 - sb[0], circle_cy + circle_r + 28),
        sub_text,
        fill=_MUTED,
        font=sub_font,
    )

    base_url = str(report.get("base_url") or "")
    base_url_disp = base_url if len(base_url) <= 40 else base_url[:37] + "..."
    bb = d.textbbox((0, 0), base_url_disp, font=sub_font)
    bw = bb[2] - bb[0]
    d.text(
        (circle_cx - bw / 2 - bb[0], circle_cy + circle_r + 56),
        base_url_disp,
        fill=_TEXT,
        font=sub_font,
    )

    attr_font = _load_font(14, bold=False, locale=loc)
    attr_text = lt(
        loc,
        "CLODEX Check · check.clodex.xyz",
        "CLODEX Check · check.clodex.xyz",
        "由 check.clodex.xyz 生成",
    )
    ab = d.textbbox((0, 0), attr_text, font=attr_font)
    aw = ab[2] - ab[0]
    d.text(
        (circle_cx - aw / 2 - ab[0], circle_cy + circle_r + 98),
        attr_text,
        fill=_MUTED,
        font=attr_font,
    )

    # ------- right: detector rows -------
    rows_x = 610
    rows_top = 132
    rows_w = W - rows_x - 60

    by_name: dict[str, dict[str, Any]] = {
        r.get("name"): r for r in report.get("results", [])
        if isinstance(r, dict)
    }

    labels = [
        (name, label)
        for name, label in detector_display(loc, protocol)
        if name != "long_context" or (by_name.get("long_context") or {}).get("status") != "skip"
    ]
    row_h = min(54, max(35, int(650 / max(1, len(labels)))))
    ultra_compact = len(labels) >= 15
    compact = len(labels) >= 13
    label_font = _load_font(15 if ultra_compact else (17 if compact else 19), bold=False, locale=loc)
    status_font = _load_font(14 if ultra_compact else (16 if compact else 18), bold=True, locale=loc)
    icon_r = 9 if ultra_compact else (11 if compact else 13)
    text_y_off = 9 if ultra_compact else (10 if compact else 12)

    for i, (name, label) in enumerate(labels):
        ry = rows_top + i * row_h
        result = by_name.get(name) or {}
        status = str(result.get("status") or "skip")
        score_v = float(result.get("score", 0.0))
        color = _status_color(status, score_v)
        st_key = "warn" if (status == "fail" and score_v >= 70) else status
        status_text = status_short(loc, st_key, name)

        icon_cx = rows_x + 20
        icon_cy = ry + row_h // 2
        if status == "pass":
            _draw_check(d, icon_cx, icon_cy, icon_r, color)
        elif status == "skip":
            d.ellipse(
                (icon_cx - icon_r, icon_cy - icon_r, icon_cx + icon_r, icon_cy + icon_r),
                outline=_MUTED,
                width=2,
            )
        else:
            _draw_cross(d, icon_cx, icon_cy, icon_r, color)

        d.text(
            (rows_x + 48, ry + row_h // 2 - text_y_off),
            label,
            fill=_TEXT,
            font=label_font,
        )

        sb2 = d.textbbox((0, 0), status_text, font=status_font)
        sw2 = sb2[2] - sb2[0]
        d.text(
            (rows_x + rows_w - sw2 - sb2[0], ry + row_h // 2 - text_y_off),
            status_text,
            fill=color,
            font=status_font,
        )

        if i < len(labels) - 1:
            d.line(
                [(rows_x, ry + row_h), (rows_x + rows_w, ry + row_h)],
                fill=_LINE,
                width=1,
            )

    note = _jpg_note(report, loc)
    if note:
        note_font = _load_font(16, bold=False, locale=loc)
        note_y = min(H - 220, rows_top + len(labels) * row_h + 22)
        d.rounded_rectangle(
            (rows_x, note_y, rows_x + rows_w, note_y + 48),
            radius=10,
            fill=(42, 31, 13),
            outline=(120, 82, 22),
            width=1,
        )
        d.text(
            (rows_x + 16, note_y + 14),
            note[:72],
            fill=(252, 211, 77),
            font=note_font,
        )

    # ------- bottom: metric tiles -------
    perf = report.get("performance") or {}
    usage = perf.get("usage") or {}
    ttft = perf.get("ttft_ms")
    metrics = [
        (lt(loc, "ПЕРВЫЙ ТОКЕН", "FIRST TOKEN", "首 TOKEN"), f"{_format_count(ttft)}ms" if ttft is not None else "—"),
        (lt(loc, "ВРЕМЯ", "TOTAL LATENCY", "总耗时"), f"{_format_count(perf.get('total_latency_ms'))}ms"),
        (lt(loc, "СКОРОСТЬ T/S", "THROUGHPUT T/S", "吞吐 T/S"), _format_count(_tokens_per_second(report))),
        (lt(loc, "ВХОД TOKENS", "INPUT TOKENS", "输入 TOKENS"), _format_count(usage.get("input_tokens"))),
        (lt(loc, "ВЫХОД TOKENS", "OUTPUT TOKENS", "输出 TOKENS"), _format_count(usage.get("output_tokens"))),
    ]
    tile_y = H - 146
    tile_h = 88
    tile_gap = 14
    tile_total_w = W - 120
    tile_w = (tile_total_w - tile_gap * (len(metrics) - 1)) // len(metrics)
    for i, (label, value) in enumerate(metrics):
        tx = 60 + i * (tile_w + tile_gap)
        highlight = False
        if i == 0 and ttft is not None and ttft > 2000:
            highlight = True
        if i == 1 and (perf.get("total_latency_ms") or 0) > 30000:
            highlight = True
        _draw_metric_tile(d, tx, tile_y, tile_w, tile_h, label, value, loc, highlight=highlight)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()

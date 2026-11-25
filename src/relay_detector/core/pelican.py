"""Pelican-on-a-bicycle SVG benchmark: strict XSS sanitizer and geometric scorer.

Inspired by Simon Willison's famous visual LLM spatial-reasoning test
("Generate an SVG of a pelican riding a bicycle"). Cheap or substituted models
emit broken XML or 3-5 crude primitives; authentic frontier models emit clean
multi-layered SVGs with wheels, frame, beak/pouch, and distinct color palette.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any


PELICAN_PROMPT = (
    "Generate an SVG of a pelican riding a bicycle. "
    "Return ONLY valid standalone SVG markup starting with <svg and ending with </svg>, "
    'with a clear viewBox="0 0 400 300" and rich colorful vector shapes '
    "(wheels, bicycle frame, pedals, handlebars, pelican body, wings, and large beak pouch). "
    "Do not include any explanation or markdown outside the SVG."
)

MAX_SVG_BYTES = 48_000

_SVG_NS = "http://www.w3.org/2000/svg"

_ALLOWED_TAGS = frozenset({
    "svg",
    "g",
    "use",
    "symbol",
    "path",
    "circle",
    "ellipse",
    "rect",
    "line",
    "polyline",
    "polygon",
    "defs",
    "lineargradient",
    "radialgradient",
    "stop",
    "clippath",
    "mask",
    "pattern",
    "title",
    "desc",
    "text",
    "tspan",
})

_DRAWING_PRIMITIVES = frozenset({
    "path",
    "circle",
    "ellipse",
    "rect",
    "line",
    "polyline",
    "polygon",
    "use",
})

_ALLOWED_ATTRS = frozenset({
    "viewbox",
    "width",
    "height",
    "xmlns",
    "id",
    "d",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "points",
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-opacity",
    "opacity",
    "transform",
    "offset",
    "stop-color",
    "stop-opacity",
    "gradientunits",
    "gradienttransform",
    "spreadmethod",
    "clip-path",
    "clippathunits",
    "mask",
    "maskunits",
    "patternunits",
    "fx",
    "fy",
    "font-size",
    "font-family",
    "font-weight",
    "text-anchor",
    "dx",
    "dy",
    "preserveaspectratio",
})

# Canonical SVG attribute casing for attributes that are case-sensitive in XML/SVG.
_CANONICAL_ATTR_CASE = {
    "viewbox": "viewBox",
    "gradientunits": "gradientUnits",
    "gradienttransform": "gradientTransform",
    "spreadmethod": "spreadMethod",
    "clippathunits": "clipPathUnits",
    "maskunits": "maskUnits",
    "patternunits": "patternUnits",
    "preserveaspectratio": "preserveAspectRatio",
}

_CANONICAL_TAG_CASE = {
    "lineargradient": "linearGradient",
    "radialgradient": "radialGradient",
    "clippath": "clipPath",
}

_DANGEROUS_VALUE_RE = re.compile(
    r"(?i)(javascript:|vbscript:|data:|expression\s*\(|url\s*\(\s*['\"]?\s*(?!#))"
)
_LOCAL_FRAGMENT_REF_RE = re.compile(r"^#[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_MAX_USE_ELEMENTS = 40
_SVG_EXTRACT_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _sanitize_element(el: ET.Element, stats: dict[str, Any]) -> ET.Element | None:
    raw_tag = _strip_ns(el.tag).lower()
    if raw_tag not in _ALLOWED_TAGS:
        return None

    if raw_tag == "use":
        if stats.get("use_count", 0) >= _MAX_USE_ELEMENTS:
            return None
        raw_href = (el.attrib.get("href") or el.attrib.get(_XLINK_HREF) or "").strip()
        if not _LOCAL_FRAGMENT_REF_RE.match(raw_href):
            return None
        stats["use_count"] = stats.get("use_count", 0) + 1

    clean_tag = _CANONICAL_TAG_CASE.get(raw_tag, raw_tag)
    out = ET.Element(clean_tag)

    for k, v in el.attrib.items():
        if k == _XLINK_HREF:
            if raw_tag == "use":
                val = str(v).strip()
                if _LOCAL_FRAGMENT_REF_RE.match(val):
                    out.set("href", val)
            continue
        if "}" in k:
            continue
        lk = k.lower()
        if lk == "href":
            if raw_tag == "use":
                val = str(v).strip()
                if _LOCAL_FRAGMENT_REF_RE.match(val):
                    out.set("href", val)
            continue
        if lk.startswith("on") or lk not in _ALLOWED_ATTRS:
            continue
        val = str(v).strip()
        if _DANGEROUS_VALUE_RE.search(val):
            continue
        out_key = _CANONICAL_ATTR_CASE.get(lk, lk)
        out.set(out_key, val)

        if lk in {"fill", "stroke", "stop-color"}:
            norm_c = val.lower()
            if norm_c and norm_c not in {"none", "transparent", "inherit"} and not norm_c.startswith("url("):
                stats["colors"].add(norm_c)

    if raw_tag in _DRAWING_PRIMITIVES:
        stats["primitive_count"] += 1
        if raw_tag in {"circle", "ellipse"}:
            stats["round_count"] += 1
        elif raw_tag == "path":
            stats["path_count"] += 1

    if el.text and raw_tag in {"title", "desc", "text", "tspan"}:
        out.text = el.text[:120]

    for child in list(el):
        sanitized_child = _sanitize_element(child, stats)
        if sanitized_child is not None:
            out.append(sanitized_child)

    return out


def extract_and_evaluate_pelican_svg(raw_text: str) -> dict[str, Any]:
    """Extract, strictly sanitize, and score a model-generated pelican SVG."""
    if not raw_text or not isinstance(raw_text, str):
        return {
            "valid_svg": False,
            "score": 0.0,
            "status": "fail",
            "reason": "empty response",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": 0,
            "svg_sanitized": "",
        }

    # Reject XML entity / DTD declarations outright before extraction/parsing.
    if re.search(r"(?i)<!(?:doctype|entity)", raw_text):
        return {
            "valid_svg": False,
            "score": 0.0,
            "status": "fail",
            "reason": "disallowed XML DOCTYPE/ENTITY",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": 0,
            "svg_sanitized": "",
        }

    match = _SVG_EXTRACT_RE.search(raw_text)
    if not match:
        return {
            "valid_svg": False,
            "score": 0.0,
            "status": "fail",
            "reason": "no <svg>...</svg> markup found",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": 0,
            "svg_sanitized": "",
            "response_excerpt": raw_text[:240],
        }

    candidate = match.group(0)
    if len(candidate.encode("utf-8")) > MAX_SVG_BYTES * 2:
        return {
            "valid_svg": False,
            "score": 0.0,
            "status": "fail",
            "reason": "svg payload exceeded size limit",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": len(candidate.encode("utf-8")),
            "svg_sanitized": "",
        }

    try:
        parsed = ET.fromstring(candidate)
    except ET.ParseError as exc:
        return {
            "valid_svg": False,
            "score": 10.0,
            "status": "fail",
            "reason": f"malformed SVG XML: {exc}",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": len(candidate.encode("utf-8")),
            "svg_sanitized": "",
        }

    if _strip_ns(parsed.tag).lower() != "svg":
        return {
            "valid_svg": False,
            "score": 0.0,
            "status": "fail",
            "reason": "root element is not <svg>",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": 0,
            "svg_sanitized": "",
        }

    stats: dict[str, Any] = {
        "primitive_count": 0,
        "round_count": 0,
        "path_count": 0,
        "colors": set(),
    }
    clean_root = _sanitize_element(parsed, stats)
    if clean_root is None:
        return {
            "valid_svg": False,
            "score": 0.0,
            "status": "fail",
            "reason": "sanitization rejected root",
            "primitive_count": 0,
            "unique_colors": 0,
            "svg_bytes": 0,
            "svg_sanitized": "",
        }

    clean_root.set("xmlns", _SVG_NS)
    has_viewbox = bool(clean_root.get("viewBox"))
    if not has_viewbox:
        w = re.sub(r"[^0-9.]", "", clean_root.get("width", "") or "") or "400"
        h = re.sub(r"[^0-9.]", "", clean_root.get("height", "") or "") or "300"
        clean_root.set("viewBox", f"0 0 {w} {h}")
        has_viewbox = bool(clean_root.get("width") and clean_root.get("height"))

    sanitized_svg = ET.tostring(clean_root, encoding="unicode")
    svg_bytes = len(sanitized_svg.encode("utf-8"))
    if svg_bytes > MAX_SVG_BYTES:
        sanitized_svg = ""

    prim = stats["primitive_count"]
    round_cnt = stats["round_count"]
    path_cnt = stats["path_count"]
    unique_colors = len(stats["colors"])
    has_wheels = round_cnt >= 2 or (round_cnt >= 1 and path_cnt >= 4)

    # Objective structural complexity score (0..100).
    score = 25.0  # valid parsed SVG
    if has_viewbox:
        score += 10.0
    if prim >= 18:
        score += 30.0
    elif prim >= 10:
        score += 22.0
    elif prim >= 5:
        score += 12.0
    elif prim >= 1:
        score += 5.0

    if has_wheels:
        score += 15.0
    elif round_cnt >= 1 or path_cnt >= 2:
        score += 7.0

    if unique_colors >= 3:
        score += 10.0
    elif unique_colors >= 2:
        score += 5.0

    if svg_bytes >= 800:
        score += 10.0
    elif svg_bytes >= 400:
        score += 5.0

    score = min(100.0, score)
    status = "pass" if score >= 70.0 and prim >= 5 else "fail"
    return {
        "valid_svg": True,
        "score": score,
        "status": status,
        "view_box": clean_root.get("viewBox", ""),
        "primitive_count": prim,
        "round_count": round_cnt,
        "path_count": path_cnt,
        "unique_colors": unique_colors,
        "has_wheels": has_wheels,
        "svg_bytes": svg_bytes,
        "svg_sanitized": sanitized_svg,
    }

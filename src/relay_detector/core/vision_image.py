"""Dynamic in-memory PNG Vision probe (impossible to pre-cache or fake).

Renders a fresh random verification code (e.g. VRF-7492) onto a crisp
high-contrast PNG using Pillow and checks whether the target model can
actually read the image via native multimodal vision.
"""

from __future__ import annotations

import base64
import io
import re
import secrets
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


VISION_PROMPT = (
    "Read the exact verification code printed in the center of this image "
    "(format VRF-XXXX). Reply with the code ONLY and nothing else."
)

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _load_vision_font(size: int = 44) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def generate_vision_challenge() -> tuple[str, str]:
    """Return (expected_code, png_base64) with a fresh per-run random code."""
    # Digits 2-9 only to prevent any O/0 or I/1 OCR ambiguity.
    digits = "".join(secrets.choice("23456789") for _ in range(4))
    code = f"VRF-{digits}"

    W, H = 380, 120
    img = Image.new("RGB", (W, H), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    # Clean frame + high-contrast text
    draw.rounded_rectangle((8, 8, W - 8, H - 8), radius=14, fill=(255, 255, 255), outline=(15, 23, 42), width=3)
    font = _load_vision_font(46)
    bbox = draw.textbbox((0, 0), code, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (W - tw) / 2 - bbox[0]
    ty = (H - th) / 2 - bbox[1]
    draw.text((tx, ty), code, fill=(15, 23, 42), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return code, b64


def evaluate_vision_response(expected_code: str, response_text: str) -> dict[str, Any]:
    raw = (response_text or "").strip()
    norm_raw = re.sub(r"[^A-Z0-9]", "", raw.upper())
    norm_exp = re.sub(r"[^A-Z0-9]", "", expected_code.upper())
    digits_exp = expected_code.split("-")[-1]

    exact = norm_exp in norm_raw
    digits_only = digits_exp in norm_raw
    if exact:
        score = 100.0
        status = "pass"
        verdict = "exact_match"
    elif digits_only:
        score = 80.0
        status = "pass"
        verdict = "digits_matched"
    else:
        score = 0.0
        status = "fail"
        verdict = "vision_failed"

    return {
        "score": score,
        "status": status,
        "expected_code": expected_code,
        "response_text": raw[:160],
        "verdict": verdict,
        "exact_match": exact,
    }

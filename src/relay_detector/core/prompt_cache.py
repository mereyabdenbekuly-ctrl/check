"""Deterministic ~2,200-token cacheable corpus for Prompt Caching probes."""

from __future__ import annotations

import secrets


def build_cacheable_system_corpus(run_salt: str | None = None) -> str:
    """Return a deterministic ~2,200-token technical specification block.

    Exceeds both OpenAI's 1,024-token automatic prompt-cache threshold and
    Anthropic's 2,048-token cache floor (Haiku 4.5 / 5.5) while using a
    per-run salt so repeat checks reliably observe a fresh cache write on
    request 1 followed by a cache read hit on request 2.
    """
    salt = run_salt or secrets.token_hex(4)
    header = (
        f"CLODEX Check Prompt Caching Verification Corpus [session={salt}]\n"
        "Follow the user instruction at the end precisely. "
        "Below is a reference telemetry catalog used solely to verify prompt prefix caching.\n\n"
    )
    sections: list[str] = []
    for idx in range(1, 46):
        sections.append(
            f"Section {idx:02d} (node-{salt}-{idx:02d}): "
            f"The distributed gateway router tracks protocol conformance across stream frames, "
            f"header canonicalization, schema validation, and backpressure thresholds. "
            f"Each partition maintains deterministic checksum window W{idx:02d} with retry budget "
            f"{idx * 3}ms, circuit threshold {60 + (idx % 35)}%, and audit marker M-{salt}-{idx:03d}.\n"
        )
    return header + "".join(sections)

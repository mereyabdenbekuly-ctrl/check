"""Streaming throughput (tok/s) and fake-stream / chunk-burst analyzer."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamSample:
    """Timing measurements from a single SSE streaming response."""

    ttft_ms: int | None = None
    last_delta_ms: int | None = None
    chunk_count: int = 0
    text_chars: int = 0
    output_tokens: int | None = None
    chunk_times_ms: list[int] = field(default_factory=list)

    def record_delta(self, elapsed_ms: int, text: str = "") -> None:
        if self.ttft_ms is None:
            self.ttft_ms = elapsed_ms
        self.last_delta_ms = elapsed_ms
        self.chunk_count += 1
        self.text_chars += len(text)
        self.chunk_times_ms.append(elapsed_ms)

    def finalize(self) -> dict[str, Any] | None:
        if self.ttft_ms is None or self.chunk_count == 0:
            return None
        last_ms = self.last_delta_ms if self.last_delta_ms is not None else self.ttft_ms
        generation_ms = max(0, last_ms - self.ttft_ms)
        tokens = self.output_tokens
        if tokens is None or tokens <= 0:
            tokens = max(1, round(self.text_chars / 3.8)) if self.text_chars > 0 else 0

        gaps = [
            max(0, self.chunk_times_ms[i] - self.chunk_times_ms[i - 1])
            for i in range(1, len(self.chunk_times_ms))
        ]
        median_gap_ms = round(statistics.median(gaps), 1) if gaps else 0.0
        max_gap_ms = max(gaps) if gaps else 0

        tps: float | None = None
        if tokens >= 3 and generation_ms >= 40:
            tps = round(tokens * 1000.0 / generation_ms, 1)
        elif tokens >= 2 and last_ms >= 50:
            # Very short stream where all tokens arrived within 1-2 chunks
            tps = round(tokens * 1000.0 / max(generation_ms, 50), 1) if generation_ms > 0 else None

        # Detect buffered / fake streams: a substantial output (>= 12 tokens or
        # >= 48 chars) that waited > 500ms for first byte and then dumped in a
        # single chunk or in < 25ms total generation window.
        verdict = "short_stream"
        if tokens >= 12 or self.text_chars >= 48:
            if self.chunk_count <= 1 or (generation_ms < 25 and self.ttft_ms >= 500):
                verdict = "buffered_burst"
            elif self.chunk_count >= 3 and generation_ms >= 30:
                verdict = "real_stream"
            else:
                verdict = "short_stream"
        elif self.chunk_count >= 3 and generation_ms >= 30:
            verdict = "real_stream"

        return {
            "ttft_ms": self.ttft_ms,
            "generation_ms": generation_ms,
            "chunk_count": self.chunk_count,
            "text_chars": self.text_chars,
            "output_tokens": tokens,
            "tokens_per_second": tps,
            "median_gap_ms": median_gap_ms,
            "max_gap_ms": max_gap_ms,
            "verdict": verdict,
        }


def summarize_stream_samples(
    samples: list[dict[str, Any]],
) -> tuple[float | None, dict[str, Any] | None]:
    """Aggregate per-stream metrics into report-level throughput & stream verdict.

    Prefers richer streams (more tokens / chunks) so a 1-token `"ok"` probe
    does not distort the real generation throughput measured on longer streams.
    """
    valid = [s for s in samples if isinstance(s, dict) and s.get("chunk_count", 0) > 0]
    if not valid:
        return None, None

    # Sort richest streams first (highest output_tokens, then chunk_count).
    ranked = sorted(
        valid,
        key=lambda s: (
            s.get("verdict") == "real_stream",
            s.get("output_tokens") or 0,
            s.get("chunk_count") or 0,
        ),
        reverse=True,
    )
    primary = ranked[0]

    # Compute true tok/s from streams that had a real measurable generation span.
    tps_candidates = [
        float(s["tokens_per_second"])
        for s in valid
        if isinstance(s.get("tokens_per_second"), (int, float))
        and (s.get("output_tokens") or 0) >= 3
        and (s.get("generation_ms") or 0) >= 40
    ]
    tps = round(statistics.median(tps_candidates), 1) if tps_candidates else primary.get("tokens_per_second")

    verdicts = [s.get("verdict") for s in valid]
    if "buffered_burst" in verdicts and "real_stream" not in verdicts:
        overall_verdict = "buffered_burst"
    elif "real_stream" in verdicts:
        overall_verdict = "real_stream"
    else:
        overall_verdict = "short_stream"

    analysis = {
        "verdict": overall_verdict,
        "tokens_per_second": tps,
        "chunk_count": primary.get("chunk_count", 0),
        "generation_ms": primary.get("generation_ms", 0),
        "median_gap_ms": primary.get("median_gap_ms", 0.0),
        "max_gap_ms": primary.get("max_gap_ms", 0),
        "stream_count": len(valid),
    }
    return tps, analysis

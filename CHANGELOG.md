# Changelog

All notable changes to **CLODEX Check** are documented here.

Live service: <https://check.clodex.xyz> ·
[Claude](https://check.clodex.xyz/claude) ·
[OpenAI](https://check.clodex.xyz/openai) ·
[Gemini](https://check.clodex.xyz/gemini) ·
[Pelican SVG](https://check.clodex.xyz/pelican) ·
[Compare](https://check.clodex.xyz/compare)

## [2.4.0] - 2026-11-25

### Added
- **Dedicated Pelican SVG Benchmark (`/pelican`) & per-model Pelican tabs** on `/claude`, `/openai`, and `/gemini` — single streamed call (`POST /api/pelican`) with instant inline SVG preview, Light/Dark canvas toggle, TTFT, live `tok/s`, and buffered-stream detection.
- **Side-by-Side Comparison (`/compare`)** — compare any two `/r/{id}` reports with overall score delta, TTFT, live `tok/s`, per-detector diff matrix, and two Pelican SVGs side by side.
- **Dynamic PNG Vision (`vision_image`)** across Claude, OpenAI, and Gemini — renders a fresh per-run `VRF-XXXX` PNG in memory (impossible to pre-cache).
- **Dynamic Anti-Cache Reasoning (`dynamic_challenge`)** across Claude, OpenAI, and Gemini.
- **Full SEO & AI GEO suite:** `1200×630` Open Graph cover (`og-cover.png`), multilingual `hreflang` + `canonical` (`RU`/`EN`/`ZH`), `Schema.org` JSON-LD (`SoftwareApplication`, `WebApplication`, `FAQPage`, `BreadcrumbList`, `HowTo`, `TechArticle`), Yandex `Clean-param` rules, and `/llms-full.txt`.

## [2.3.0] - 2026-11-25

### Added
- **Pelican-on-a-Bicycle SVG (`pelican_svg`)** detector with strict XSS/XXE sanitizer and sandboxed `.svg` download (`/r/{id}/pelican.svg`).
- **Real Prompt Caching (`prompt_cache`)** verification for Claude and OpenAI.
- **Hidden System Prompt Injection & Token Bloat Audit (`system_injection`)** across all 3 protocols.
- **Tokenizer Edge-Case Fingerprinting (`tokenizer_probe`)** for `o200k_base` (OpenAI) and SentencePiece (Gemini).
- **True Streaming `tok/s` & Fake-Stream Detection (`StreamSample`)** distinguishing `real_stream` vs `buffered_burst`.

## [2.2.0] - 2026-11-25

### Added
- **Live Dynamic Event Log & Detector Criteria Checklist** during active runs (`running.html` + `/api/status/{id}`).
- **Dark Obsidian + `#39ff88` CLODEX UI & dark JPG report cards**.
- Full localization across Russian, English, and Chinese.

# Contributing to CLODEX Check

Thanks for helping improve **CLODEX Check** (`https://check.clodex.xyz`)! Every bug fix, new detector, and protocol edge-case test makes AI API auditing stronger for everyone.

## Quick Local Setup

```bash
git clone https://github.com/mereyabdenbekuly-ctrl/check.git
cd check
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev,web]"
./.venv/bin/pytest -q
```

Run the web server locally:

```bash
CLODEX_CHECK_JOBS_DIR=/tmp/clodex-check-dev ./.venv/bin/uvicorn web.server:app --host 127.0.0.1 --port 8088 --reload
```

## Project Layout

- `src/relay_detector/core/` — shared models, scoring engine, Pelican SVG sanitizer, Prompt Caching, system-injection audit, tokenizer probe, dynamic PNG vision, anti-cache reasoning, and live stream metrics.
- `src/relay_detector/protocols/{anthropic,openai,gemini}/` — protocol-specific HTTP/SSE clients, detectors, and runners.
- `web/` — FastAPI app, async job queue with live event stream, Pillow JPG card renderer, dark obsidian UI (RU / EN / ZH), `/pelican`, and `/compare`.
- `tests/` — pytest suite covering detectors, streaming, SVG sanitization, web routes, and SEO/GEO invariants.

## Guidelines

- **Never commit real API keys or secrets** in code, fixtures, or issues.
- **Keep `Mode.STANDARD` backwards-compatible** when adding new detectors; add heavy or new detectors to `Mode.FULL` with matching unit tests.
- **Add tests** for every bug fix or new detector and verify `./.venv/bin/pytest -q` passes cleanly before opening a PR.
- **License:** All contributions are licensed under **AGPL-3.0-or-later** (see [LICENSE](LICENSE)).

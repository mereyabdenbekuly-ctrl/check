# Security Policy · CLODEX Check

## Zero-Key-Persistence Architecture

CLODEX Check (`https://check.clodex.xyz`) is designed so you never have to blindly trust a hosted service with your API keys:

1. **RAM-only lifetime:** Your API key exists strictly in process memory for the duration of a single check job and is discarded immediately afterward.
2. **Never written to disk or logs:** Raw API keys are never serialized into report JSON, JPG cards, application logs, databases, or HTTP responses. Public `/r/{job_id}` reports retain only a masked key prefix/suffix (`sk-ab...xyz`).
3. **Strict SVG sandboxing:** Every model-generated Pelican SVG is sanitized against XSS/XXE (removing `<script>`, `<foreignObject>`, `<iframe>`, `on*` handlers, `javascript:` URLs, and `<!DOCTYPE>`/`<!ENTITY>`), rendered inside an isolated `<img src="data:image/svg+xml;base64,...">`, and served for download with `Content-Security-Policy: sandbox` and `X-Content-Type-Options: nosniff`.
4. **Full self-hosting:** If you prefer that keys never leave your own machine, run CLODEX Check locally via Docker or Python CLI from this repository.

## Official Domain

The only official hosted instance is **`https://check.clodex.xyz`** (part of **`https://clodex.xyz`**). Beware of lookalike domains.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities (such as API-key leakage, SSRF, XSS/SVG sandbox bypass, or container escape).

Report vulnerabilities privately via **GitHub Security Advisories** in `mereyabdenbekuly-ctrl/check` with:
- Reproduction steps and affected endpoint or file path
- Impact assessment
- Suggested fix (if available)

We review security reports promptly and coordinate fixes before public disclosure.

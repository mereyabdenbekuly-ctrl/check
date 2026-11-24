# CLODEX Check

**CLODEX Check** — открытый сервис (AGPL-3.0) для проверки подлинности и качества AI API-эндпоинтов и релеев. Помогает убедиться, что провайдер действительно отдаёт оригинальные модели **Claude**, **OpenAI (GPT)** или **Gemini**, а не подменяет бэкенд, не урезает контекст и не ломает протокол.

- Онлайн-версия: [check.clodex.xyz](https://check.clodex.xyz)
- Основная платформа: [clodex.xyz](https://clodex.xyz)
- Исходный код: [mereyabdenbekuly-ctrl/check](https://github.com/mereyabdenbekuly-ctrl/check)
- Основан на открытом движке [Veridrop (`relay_detector`)](https://github.com/canarybyte/veridrop) (AGPL-3.0).

## Что проверяет

- **Claude / Anthropic Messages API (12 детекторов)**: серверная криптоподпись `thinking signature` (Opus 5.5 / 5 / 4.8 / 4.7, Sonnet 5.5 / 5 / 4.6, Haiku 5.5 / 4.5), идентичность, поведенческий профиль, знания, PDF, `tool_use`, SSE-протокол, `msg_`/`toolu_` префиксы, stream/non-stream согласованность, `usage` + `count_tokens`, опционально long context (32k → 950k).
- **OpenAI / GPT Chat Completions (8 детекторов)**: GPT-6.2 / 6.1 / 6 / 5.6 / 5.5 / 5.4, проверка `function calling`, `response_format=json_schema (strict=true)`, stream/non-stream, отпечатки чужих бэкендов в `usage` (`claude_*`, `gemini_*`, `usage_source`), корректность биллинга токенов, опционально long context.
- **Gemini OpenAI-compatible (7 детекторов)**: Gemini 4 / 3.8 / 3 / 2.5 через `POST /chat/completions` — структура ответа, `function calling`, JSON Schema, stream и `usage`.

## Безопасность API-ключей

API-ключ используется **только в оперативной памяти** на время выполнения проверки и сразу очищается. Ключ не сохраняется в report JSON, логи, базу данных или на диск. В публичных отчётах `/r/{id}` и JPG-карточках показывается только маска ключа.

Если вы не хотите передавать ключ публичному сервису — запустите проект локально через Python или Docker.

## Быстрый старт (Docker)

```bash
git clone https://github.com/mereyabdenbekuly-ctrl/check.git
cd check
docker build -t clodex-check .
docker run --rm -p 127.0.0.1:8088:8088 clodex-check
```

Откройте `http://127.0.0.1:8088`.

## Быстрый старт (Python 3.10+)

```bash
git clone https://github.com/mereyabdenbekuly-ctrl/check.git
cd check
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev,web]"
./.venv/bin/uvicorn web.server:app --host 127.0.0.1 --port 8088
```

## CLI

```bash
./.venv/bin/relay-detector detect \
  --protocol anthropic \
  --base-url https://clodex.xyz \
  --api-key "$API_KEY" \
  --model claude-sonnet-5-5 \
  --mode full \
  -o out/report.json
```

```bash
./.venv/bin/relay-detector detect \
  --protocol openai \
  --base-url https://clodex.xyz/v1 \
  --api-key "$API_KEY" \
  --model gpt-6.2-sol \
  --mode standard \
  -o out/openai-report.json
```

## Тесты

```bash
./.venv/bin/pytest -q
```

## Лицензия

Проект распространяется под лицензией **AGPL-3.0-or-later**. См. [LICENSE](LICENSE).

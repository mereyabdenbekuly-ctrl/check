<div align="center">

# CLODEX Check

**Самый полный open-source аудитор подлинности AI API и прокси-релеев**  
*The most comprehensive open-source authenticity & protocol auditor for Claude, OpenAI (GPT), and Gemini API endpoints.*

[![Live Demo](https://img.shields.io/badge/Live-check.clodex.xyz-39ff88?style=flat-square&logoColor=080b09)](https://check.clodex.xyz)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square)](pyproject.toml)
[![Protocols](https://img.shields.io/badge/Protocols-Claude%20%7C%20OpenAI%20%7C%20Gemini-0f172a?style=flat-square)](https://check.clodex.xyz)

[Онлайн-сервис (`check.clodex.xyz`)](https://check.clodex.xyz) ·
[Сравнение провайдеров (`/compare`)](https://check.clodex.xyz/compare) ·
[FAQ](https://check.clodex.xyz/faq) ·
[CLODEX Platform (`clodex.xyz`)](https://clodex.xyz)

</div>

---

## Зачем это нужно / Why CLODEX Check?

Рынок AI API-релеев и агрегаторов полон скрытых подмен: дешёвые модели выдают за Claude Opus / GPT-6 / Gemini Pro, урезают окно контекста, отключают Prompt Caching, инжектируют скрытые системные промпты (за которые платите вы), буферизуют стрим вместо честного SSE или накручивают счётчики токенов.

**CLODEX Check** объединяет в одном инструменте всё, что нужно для независимого аудита любого AI API-эндпоинта за 60–80 секунд:

- **17 детекторов для Claude** (`/v1/messages`) — с криптографической проверкой серверной подписи Anthropic (`thinking signature`).
- **14 детекторов для OpenAI / GPT** (`/v1/chat/completions`) — с пробой токенизатора `o200k_base`, проверкой Prompt Caching, strict JSON Schema и поиском утечек чужих бэкендов (`claude_*` / `gemini_*`).
- **12 детекторов для Gemini** (`/chat/completions`) — с пробой токенизатора SentencePiece, function calling, JSON Schema и аудитом потока.
- **Пеликан-тест (SVG)** — потоковая генерация «пеликана на велосипеде» (методика Симона Уиллисона) со строгой XSS-санитизацией, предпросмотром Light/Dark, скачиванием `.svg` и одновременным замером реальной скорости потока.
- **Честный `tok/s` + детектор фейкового стрима** — замеряет реальную скорость генерации по межчанковым интервалам (`StreamSample`) и отличает настоящий SSE (`real_stream`) от буферизованного рывка (`buffered_burst`).
- **Динамический PNG Vision (`VRF-XXXX`)** — на каждый запуск рисует в памяти свежую картинку со случайным кодом (невозможно закэшировать), отсекая текстовые подмены и битый мультимодальный прокси.
- **Динамическая анти-кэш логика** — одноразовая задача (арифметика + посимвольный разворот случайной строки в строгом JSON) для выявления кэш-прокси и даунгрейда модели.
- **Аудит скрытых system-инъекций** — канареечный тест сохранности пользовательского `system prompt` + замер скрытого раздувания `input_tokens` на пустом запросе `hi`.
- **Проверка реального Prompt Caching** — два последовательных запроса с общим префиксом >2000 токенов проверяют реальное срабатывание `cache_read_input_tokens` / `cached_tokens`.
- **Live-консоль во время проверки** — динамический чек-лист критериев и поток событий в реальном времени (видно каждый запускаемый и завершённый детектор).
- **Сравнение провайдеров Side-by-Side (`/compare`)** — вставьте любые два отчёта `/r/{id}` и сравните скор, TTFT, `tok/s`, все детекторы и **два Пеликана SVG рядом**.
- **Постоянные отчёты + Dark JPG-карточки** — каждый запуск получает постоянный URL `/r/{id}`, JSON API `/api/result/{id}.json`, скачиваемый `.svg` и тёмную карточку `/r/{id}.jpg` для Telegram и обзоров.

---

## Матрица детекторов / Detector Matrix

| Детектор | Claude (17) | OpenAI (14) | Gemini (12) | Что выявляет |
|---|:---:|:---:|:---:|---|
| **`thinking_signature`** | ✅ (25) | — | — | Криптографическая серверная подпись Anthropic в `thinking`-блоках (500–2000 B) — невозможно подделать на стороне релея |
| **`behavioral_signature`** | ✅ (15) | — | — | Характерный стиль Claude (Markdown, списки, тон отказа) на 3 пробах |
| **`identity`** | ✅ (5) | — | — | Самоидентификация без system prompt + утечка чужих брендов |
| **`knowledge`** | ✅ (10) | — | — | 5 фактологических вопросов об Anthropic и Claude |
| **`pdf`** | ✅ (8) | — | — | Нативное чтение динамически сгенерированного PDF со случайным `MAGIC-...` токеном |
| **`basic_request`** | — | ✅ (15) | ✅ (15) | Базовая доступность, `choices`, `finish_reason`, проверка reasoning-бюджета |
| **`consistency` / `model_consistency` / `model_info`** | ✅ (10) | ✅ (15) | ✅ (15) | Совпадение `response.model` и стабильность длины на повторных запросах |
| **`structured_output` / `function_calling`** | ✅ (12) | ✅ (15+15) | ✅ (15+15) | Строгий `json_schema (strict=true)`, `tool_use` / `tool_calls`, префиксы `toolu_`, `stop_reason` |
| **`protocol`** | ✅ (5) | ✅ (15) | ✅ (15) | Пассивный аудит всех ответов на соответствие спецификации и утечки чужих полей (`claude_*`, `gemini_*`) |
| **`integrity`** | ✅ (5) | ✅ (15) | ✅ (15) | Согласованность `stream=true` (SSE) и `stream=false`: текст, `stop_reason`, токены |
| **`token_usage` / `token_billing`** | ✅ (10) | ✅ (10) | ✅ (10) | Прирост токенов, stream vs non-stream, сверка с `/v1/messages/count_tokens` |
| **`message_id`** | ✅ (5) | — | — | Проверка префиксов `msg_...` во всех ответах |
| **`tokenizer_probe`** | — | ✅ (10) | ✅ (10) | Краевые случаи токенизатора (`o200k_base` / SentencePiece): Unicode, кириллица, CJK, emoji, склейка цифр и пробелов |
| **`prompt_cache`** | ✅ (8) | ✅ (8) | — | Два последовательных вызова с общим префиксом >2000 токенов: реальный `cache_read` / `cached_tokens > 0` |
| **`system_injection`** | ✅ (6) | ✅ (6) | ✅ (6) | Канареечный тест сохранности `system prompt` + аудит скрытого раздувания `input_tokens` на голом `hi` |
| **`vision_image`** | ✅ (7) | ✅ (7) | ✅ (7) | Динамически сгенерированный PNG в памяти со случайным кодом `VRF-XXXX` (нельзя закэшировать) |
| **`dynamic_challenge`** | ✅ (6) | ✅ (6) | ✅ (6) | Одноразовая задача (арифметика + посимвольный разворот слова в JSON) против кэш-прокси и слабых моделей |
| **`pelican_svg`** | ✅ (8) | ✅ (8) | ✅ (8) | Потоковая генерация SVG «пеликан на велосипеде» + анализ геометрии + замер реальной скорости `tok/s` и детекция фейкового стрима |
| **`long_context`** *(opt-in)* | ✅ (15) | ✅ (15) | — | Тест «иголка в стоге сена» на 32k → 200k → 950k для выявления тихого урезания контекста |

> **Важно про уровни достоверности:** у Claude серверная криптоподпись `thinking signature` даёт **криптографическое** доказательство оригинальной модели. У OpenAI и Gemini в API нет аналогичной серверной подписи, поэтому 100% там означает полное прохождение всех протокольных, поведенческих, мультимодальных, кэш-, токенизаторных и визуальных проверок без следов подмены.

---

## Безопасность и приватность (Zero-Key-Persistence)

- API-ключ существует **только в оперативной памяти** на время выполнения одной задачи и сразу очищается.
- Сырой ключ **никогда не записывается** на диск, в report JSON, в логи, в базы данных или в HTTP-ответы.
- В публичных отчётах `/r/{id}` и JPG-карточках сохраняется только маска ключа (`sk-ab...xyz`).
- Все сгенерированные моделью SVG проходят строгую очистку (вырезаются `<script>`, `<foreignObject>`, `<iframe>`, `on*` обработчики, `javascript:` URL, `<!DOCTYPE>`/`<!ENTITY>`), отображаются внутри `<img src="data:image/svg+xml;base64,...">` и отдаются при скачивании с `Content-Security-Policy: sandbox`.
- Вы можете проаудировать каждую строку кода или запустить всё локально у себя — ключ не покинет вашу машину.

---

## Быстрый старт / Quickstart

### 1. Docker (1 команда)

```bash
git clone https://github.com/mereyabdenbekuly-ctrl/check.git
cd check
docker build -t clodex-check .
docker run --rm -p 127.0.0.1:8088:8088 -v "$(pwd)/data:/data" clodex-check
```

Откройте `http://127.0.0.1:8088`.

### 2. Локальный запуск (Python 3.10+)

```bash
git clone https://github.com/mereyabdenbekuly-ctrl/check.git
cd check
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev,web]"
CLODEX_CHECK_JOBS_DIR=./data/jobs ./.venv/bin/uvicorn web.server:app --host 127.0.0.1 --port 8088
```

### 3. CLI

Проверка Claude API в полном режиме:

```bash
./.venv/bin/relay-detector detect \
  --protocol anthropic \
  --base-url https://clodex.xyz \
  --api-key "$API_KEY" \
  --model claude-sonnet-5-5 \
  --mode full \
  -o out/claude-report.json
```

Проверка OpenAI / GPT API:

```bash
./.venv/bin/relay-detector detect \
  --protocol openai \
  --base-url https://clodex.xyz/v1 \
  --api-key "$API_KEY" \
  --model gpt-6.2-sol \
  --mode full \
  -o out/openai-report.json
```

Проверка Gemini API (OpenAI-compatible):

```bash
./.venv/bin/relay-detector detect \
  --protocol gemini \
  --base-url https://clodex.xyz/v1 \
  --api-key "$API_KEY" \
  --model gemini-4-neon \
  --mode full \
  -o out/gemini-report.json
```

Сравнение двух JSON-отчётов в терминале:

```bash
./.venv/bin/relay-detector compare out/provider-a.json out/provider-b.json
```

---

## Web API эндпоинты

| Метод и путь | Назначение |
|---|---|
| `POST /api/probe` | Быстрая предпроверка `/v1/models` и авторизации |
| `POST /api/detect/claude` | Запуск проверки Claude (`/v1/messages`) |
| `POST /api/detect/openai` | Запуск проверки OpenAI (`/v1/chat/completions`) |
| `POST /api/detect/gemini` | Запуск проверки Gemini (`/chat/completions`) |
| `POST /api/pelican` | Быстрый отдельный Пеликан-тест (SVG) для Claude / OpenAI / Gemini (1 потоковый запрос) |
| `GET /pelican` | Отдельная страница Пеликан-теста с живым холстом SVG и выбором протокола |
| `GET /api/status/{job_id}` | Живой статус задачи, прогресс детекторов и поток событий |
| `GET /api/result/{job_id}.json` | Полный машиночитаемый JSON-отчёт |
| `GET /r/{job_id}` | Постоянная веб-страница отчёта (включая Пеликан SVG) |
| `GET /r/{job_id}.jpg` | Готовая тёмная карточка отчёта `1400×1000` для соцсетей и Telegram |
| `GET /r/{job_id}/pelican.svg` | Скачивание очищенного SVG (`CSP: sandbox`) |
| `GET /compare?a={id1}&b={id2}` | Сравнение двух отчётов бок о бок (+ два Пеликана SVG) |
| `GET /healthz` | Healthcheck сервиса |

---

## Разработка и тесты

```bash
./.venv/bin/pytest -q
```

Структура проекта:
- `src/relay_detector/core/` — ядро, скоринг, `pelican.py`, `prompt_cache.py`, `system_injection.py`, `tokenizer_probe.py`, `vision_image.py`, `dynamic_challenge.py`, `stream_metrics.py`.
- `src/relay_detector/protocols/{anthropic,openai,gemini}/` — HTTP/SSE-клиенты, детекторы и раннеры для каждого протокола.
- `web/` — FastAPI-сервер, очередь задач с live-событиями, генератор JPG-карточек (Pillow), тёмный интерфейс RU/EN/CN и страница `/compare`.
- `tests/` — автотесты всех детекторов, стриминга, санитизации SVG, JPG-рендера и веб-эндпоинтов.

---

## Благодарности и открытые источники / Acknowledgments

CLODEX Check создан в духе открытого ПО с уважением к open-source сообществу:

- **Пеликан на велосипеде (SVG):** вдохновлён визуальным бенчмарком Симона Уиллисона ([simonw/pelican-bicycle](https://simonwillison.net/tags/pelican-riding-a-bicycle/)).
- **Методологические идеи open-source сообщества:** техники аудита Prompt Caching, скрытых system-инъекций, краевых случаев токенизатора, динамических анти-кэш задач, PNG vision и детекции буферизованных стримов реализованы под архитектуру CLODEX Check с опорой на открытые исследования сообщества (`TokenScanAI/tokenapi-scan`, `BingZi-233/check-cx`, `mintesnot-teshome/llm-verify`, `toby-bridges/api-relay-audit`).

---

## Лицензия / License

Распространяется под лицензией **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**. Подробности в [LICENSE](LICENSE).

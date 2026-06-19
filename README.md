# Clodex Check

Clodex Check — открытый сервис для проверки AI API relay и proxy endpoint-ов. Он помогает понять, действительно ли провайдер отдает заявленную модель, не ломает ли протокол, корректно ли передает streaming, usage, tool calls, structured output и другие важные поля.

Онлайн-версия: [check.clodex.xyz](https://check.clodex.xyz)

Репозиторий: [mereyabdenbekuly-ctrl/check](https://github.com/mereyabdenbekuly-ctrl/check)

## Что проверяет

- Claude / Anthropic Messages API
- OpenAI-compatible Chat Completions
- Gemini через OpenAI-compatible endpoint
- protocol shape и обязательные поля ответа
- stream и non-stream согласованность
- usage и подозрительные следы переупаковки
- tool use / function calling
- structured output
- PDF и long context проверки, если они включены пользователем
- Claude thinking signature как сильный сигнал нативного Claude passthrough

## Зачем это нужно

На рынке много API-переходников: одни честно проксируют модель, другие подменяют backend, урезают контекст, теряют usage или пересобирают ответ так, что клиенты начинают работать нестабильно.

Clodex Check запускает набор тестовых запросов и формирует отчет с оценкой, деталями по каждому detector-у и share-ссылкой. Это удобно для быстрой проверки нового поставщика, диагностики своего relay или сравнения нескольких endpoint-ов.

## Безопасность API key

API key используется только для запуска проверки. В отчеты, публичные страницы и JPG-карточки ключ не попадает. В нормальном web-flow ключ нужен только на время job-а.

Если не хотите передавать ключ публичному сервису, проект можно запустить локально или на своем сервере.

## Быстрый старт

```bash
git clone https://github.com/mereyabdenbekuly-ctrl/check.git
cd check
python3 -m venv venv
./venv/bin/pip install -e ".[dev,web]"
```

Запуск web-интерфейса:

```bash
./venv/bin/uvicorn web.server:app --host 0.0.0.0 --port 8000
```

После запуска откройте:

```text
http://localhost:8000
```

## CLI

Пример одиночной проверки Claude relay:

```bash
./venv/bin/relay-detector detect \
  --protocol anthropic \
  --base-url https://api.example.com/v1 \
  --api-key "$API_KEY" \
  --model claude-sonnet-4-6 \
  --mode full \
  -o out/report.json
```

Пример проверки OpenAI-compatible relay:

```bash
./venv/bin/relay-detector detect \
  --protocol openai \
  --base-url https://api.example.com/v1 \
  --api-key "$API_KEY" \
  --model gpt-5.5 \
  --mode full \
  -o out/openai-report.json
```

## Режимы проверки

- `quick` — короткая базовая проверка.
- `standard` — больше protocol и behavior тестов.
- `full` — полный набор detector-ов.

Long context и extreme context могут стоить дороже, потому что отправляют большие prompts. Включайте их только когда реально нужно проверить заявленный context window.

## Web-страницы

- `/` — главная страница
- `/claude` — проверка Claude relay
- `/openai` — проверка OpenAI-compatible relay
- `/gemini` — проверка Gemini relay
- `/leaderboard` — публичные отчеты и рейтинг relay
- `/r/{id}` — публичная страница отчета
- `/r/{id}.jpg` — JPG-карточка отчета
- `/faq` — вопросы и пояснения по проверкам

## Структура проекта

```text
src/relay_detector/        detector-ы, CLI и протокольная логика
web/                       FastAPI web-приложение и шаблоны
web/static/                CSS, JS, robots, sitemap
web/templates/             HTML-шаблоны
data/baselines/            базовые профили для сравнения
tests/                     тесты detector-ов и web-логики
```

## Деплой

В репозитории есть `deploy.sh`, но в публичной версии нет зашитого сервера. Хост нужно передавать явно:

```bash
./deploy.sh --host user@example.com --path /opt/check
```

Или через переменные:

```bash
RELAY_DETECTOR_HOST=user@example.com RELAY_DETECTOR_PATH=/opt/check ./deploy.sh
```

## Лицензия

Проект распространяется под AGPL-3.0. См. [LICENSE](LICENSE).

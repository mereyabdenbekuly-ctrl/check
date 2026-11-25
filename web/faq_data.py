"""Localized FAQ content for /faq and FAQPage JSON-LD."""

from __future__ import annotations

from dataclasses import dataclass

from .i18n import normalize_locale


@dataclass(frozen=True)
class FAQEntry:
    id: str
    q: str
    a: str


@dataclass(frozen=True)
class FAQCategory:
    id: str
    title: str
    intro: str
    entries: tuple[FAQEntry, ...]


def _category(id: str, title: str, intro: str, entries: tuple[tuple[str, str, str], ...]) -> dict[str, object]:
    return {"id": id, "title": title, "intro": intro, "entries": entries}


_FAQ_DATA: dict[str, tuple[dict[str, object], ...]] = {
    "ru": (
        _category("basics", "Основы relay", "Что такое AI API relay, зачем он нужен и где основные риски.", (
            ("what-is-relay", "Что такое AI API relay?", "Это промежуточный API-сервис, который принимает ваш запрос и пересылает его к OpenAI, Anthropic, Google или другому поставщику. Хороший relay работает почти как прозрачный proxy; плохой может менять модель, поля ответа или usage."),
            ("why-use-relay", "Зачем вообще пользоваться relay?", "Обычно ради единого API для разных моделей, цены, доступности или корпоративной маршрутизации. Но relay становится доверенной прослойкой, поэтому его нужно проверять."),
            ("relay-vs-official", "Чем relay отличается от официального API?", "Официальный API имеет стабильные поля, ошибки и billing. Relay может быть 1:1 passthrough, а может перепаковывать ответы, скрывать usage, отключать функции или подменять backend."),
            ("relay-risk", "Какие риски у relay?", "Главные риски: недоступность сервиса, подмена модели, неправильный billing, запись prompt-ов и потеря возможностей вроде tools, PDF или structured output."),
        )),
        _category("authenticity", "Подлинность моделей", "Как Clodex ищет подмену Claude, GPT и Gemini.", (
            ("verify-authentic", "Как понять, что модель настоящая?", "Clodex смотрит на три группы сигналов: protocol shape, capability probes и usage fingerprints. Для Claude дополнительно используется thinking signature — самый сильный сигнал."),
            ("fake-tactics", "Как relay обычно подменяет модели?", "Например, продаёт GPT, но отправляет запрос в Claude backend; продаёт Claude, но маршрутизирует через Bedrock-like слой без thinking signature; или отключает advanced features и возвращает только обычный текст."),
            ("ask-who-are-you", "Можно просто спросить модель, кто она?", "Нет. Ответ на вопрос об идентичности легко подделать system prompt-ом. Надёжнее смотреть на поля протокола, signatures, tool calls и usage."),
        )),
        _category("claude", "Claude relay", "Claude проверяется глубже всего благодаря thinking signature (17 детекторов).", (
            ("thinking-signature", "Что такое thinking signature?", "Это криптографическая серверная подпись Anthropic в thinking response. Relay теоретически не может сгенерировать её сам, поэтому отсутствие или странная форма signature — сильный сигнал проблемы."),
            ("claude-coverage", "Что проверяет Claude detector?", "17 детекторов: thinking signature, identity, поведенческий отпечаток, знания, нативный PDF, tool use / structured output, протокол, stream/non-stream, message IDs, usage + count_tokens, Prompt Caching, аудит system-инъекций, динамический PNG Vision, анти-кэш логика, Пеликан-тест SVG и опциональный long context до 950k."),
            ("claude-cost", "Проверка тратит токены?", "Да. CLODEX Check отправляет реальные запросы к вашему эндпоинту. Стоимость списывает проверяемый провайдер, не CLODEX Check."),
        )),
        _category("advanced", "Пеликан-тест, кэш, токенизатор и сравнение", "Продвинутые проверки подлинности, скорости и качества AI API.", (
            ("pelican-svg", "Что такое Пеликан-тест (SVG) и зачем он нужен?", "Это визуальный бенчмарк Симона Уиллисона: модель за один потоковый запрос рисует пеликана на велосипеде в SVG. По геометрии, количеству фигур, цветовой палитре и колёсам сразу видно уровень модели — слабую подмену видно глазами. Доступен отдельной вкладкой на странице каждой модели и на /pelican."),
            ("fake-stream", "Как CLODEX Check находит «фейковый» стрим и измеряет tok/s?", "На каждом потоковом запросе мы записываем точные метки времени прихода чанков (StreamSample). Реальная скорость tok/s считается по времени генерации после первого токена, а если весь текст пришёл одним рывком после паузы — стрим помечается как буферизованный (buffered_burst)."),
            ("prompt-cache-check", "Как проверяется реальный Prompt Caching?", "Отправляются два последовательных запроса с одинаковым префиксом >2000 токенов. Настоящий Prompt Caching возвращает cache_read_input_tokens > 0 (Claude) или cached_tokens > 0 (OpenAI). Если там 0 — провайдер отбрасывает кэш или раскидывает запросы по разным аккаунтам."),
            ("system-injection-check", "Что ищет аудит скрытых system-инъекций?", "Во-первых, канареечный тест проверяет, доходит ли ваш system prompt до модели без перезаписи. Во-вторых, пустой запрос «hi» выявляет скрытую обёртку промпта, из-за которой вы переплачиваете за лишние входные токены."),
            ("compare-providers", "Как сравнить двух AI API-провайдеров на /compare?", "Прогоните два провайдера (или две модели) и вставьте их ссылки /r/{id} на странице /compare — увидите разницу баллов, TTFT, tok/s, матрицу всех детекторов и два Пеликана SVG рядом."),
        )),
        _category("openai", "OpenAI / GPT relay", "OpenAI проверяется на уровне поведения, протокола и fingerprints.", (
            ("openai-proof", "Можно криптографически доказать настоящий GPT?", "Нет, OpenAI responses не содержат аналога Claude thinking signature. Поэтому Clodex ищет protocol compliance, capability support и подозрительные usage-поля."),
            ("openai-fingerprint", "Как поймать GPT -> Claude подмену?", "Часто в OpenAI-shaped response просачиваются Anthropic-style поля: input_tokens/output_tokens, usage_source, claude_cache_* и другие следы адаптера."),
            ("openai-no-models", "Почему найдено 0 GPT-моделей?", "Возможно, key куплен только для Claude или Gemini группы. Preflight показывает, есть ли модели другого протокола, и предлагает перейти на нужную страницу."),
        )),
        _category("gemini", "Gemini relay", "Gemini проверяется через OpenAI-compatible endpoint.", (
            ("gemini-path", "Почему используется OpenAI-compatible path?", "Большинство Gemini relay exposes /chat/completions compatibility. Это позволяет проверять function calling, JSON schema, stream и usage единообразно."),
            ("gemini-model-not-found", "Почему часто model_not_found?", "Relay может поддерживать только часть моделей, использовать другое имя или уже убрать preview-модель. Preflight помогает увидеть доступные варианты."),
            ("gemini-official", "Можно проверить официальный Google Gemini?", "Да. Используйте base_url <code>https://generativelanguage.googleapis.com/v1beta/openai</code> и AIza... key из Google AI Studio."),
        )),
        _category("privacy", "Приватность и безопасность", "Что происходит с API key и отчётами.", (
            ("key-stored", "Clodex сохраняет мой API key?", "Нет. Key используется во время job-а и не пишется в report JSON, логи или базу. В отчёте остаётся только маска."),
            ("report-public", "Кто видит отчёт /r/xxx?", "Любой, у кого есть ссылка. Не делитесь URL, если проверяете приватный relay и не хотите публиковать результат."),
            ("self-host", "Можно self-host?", "Да. Проект open source, его можно поднять у себя и держать API keys внутри своей сети."),
        )),
    ),
    "en": (
        _category("basics", "Relay Basics", "What an AI API relay is, why people use it, and where the risks are.", (
            ("what-is-relay", "What is an AI API relay?", "It is an intermediate API service that receives your request and forwards it to OpenAI, Anthropic, Google, or another provider. A good relay behaves like a transparent proxy; a bad one may change the model, response fields, or usage."),
            ("why-use-relay", "Why use a relay?", "Common reasons are unified APIs, pricing, availability, or corporate routing. But the relay becomes a trusted middle layer, so it should be checked."),
            ("relay-vs-official", "How is a relay different from an official API?", "Official APIs have stable fields, errors, and billing. Relays may be 1:1 passthrough, or they may rewrap responses, hide usage, disable capabilities, or swap backends."),
            ("relay-risk", "What are the risks?", "The main risks are downtime, model substitution, incorrect billing, prompt logging, and missing capabilities such as tools, PDF, or structured output."),
        )),
        _category("authenticity", "Model Authenticity", "How Clodex looks for Claude, GPT, and Gemini substitution.", (
            ("verify-authentic", "How do I know the model is real?", "Clodex looks at protocol shape, capability probes, and usage fingerprints. For Claude, it also uses thinking signature, the strongest signal."),
            ("fake-tactics", "How do relays fake models?", "For example, a relay may sell GPT while forwarding to Claude, sell Claude through a Bedrock-like layer without thinking signatures, or disable advanced features and return plain text only."),
            ("ask-who-are-you", "Can I just ask the model who it is?", "No. Identity answers are easy to spoof with a system prompt. Protocol fields, signatures, tool calls, and usage are more reliable."),
        )),
        _category("claude", "Claude Relay", "Claude is audited deepest via server-side thinking signatures (17 detectors).", (
            ("thinking-signature", "What is a Claude thinking signature?", "It is a server-side cryptographic signature from Anthropic on Claude thinking blocks. A relay cannot forge it, so missing or malformed signatures are a strong warning sign."),
            ("claude-coverage", "What does the Claude detector suite check?", "17 detectors: thinking signature, identity, behavior, knowledge, native PDF, tool use / structured output, protocol, stream parity, message IDs, usage + count_tokens, Prompt Caching, hidden system-prompt audit, dynamic PNG vision, anti-cache reasoning, Pelican SVG benchmark, and optional long context up to 950k."),
            ("claude-cost", "Does the check spend tokens?", "Yes. CLODEX Check sends live diagnostic requests to your endpoint. Token usage is billed by the tested provider, never by CLODEX Check."),
        )),
        _category("advanced", "Pelican SVG, Prompt Caching, Streaming & Compare", "Advanced authenticity, throughput, and side-by-side comparison probes.", (
            ("pelican-svg", "What is the Pelican-on-a-bicycle SVG test?", "Simon Willison's visual benchmark asks the model to draw a pelican riding a bicycle in pure SVG in a single streamed call. Vector geometry, primitive richness, and visual quality make silent downgrades immediately obvious. Available as a dedicated tab on every model page and at /pelican."),
            ("fake-stream", "How does CLODEX Check detect buffered fake streams and measure tok/s?", "Every streamed probe records chunk arrival timestamps (StreamSample). Live throughput tok/s is measured strictly over generation time after TTFT, and single-burst buffered proxies are flagged as buffered_burst."),
            ("prompt-cache-check", "How is Prompt Caching verified?", "Two back-to-back calls with an identical >2,000-token prefix verify real cache_read_input_tokens > 0 (Claude) or cached_tokens > 0 (OpenAI). Zero cache reads signal stripped cache headers or cross-account rotation."),
            ("system-injection-check", "What does the hidden system-prompt audit catch?", "A random canary rule verifies your system prompt reaches the model intact, while a bare 'hi' request detects hidden wrapper prompts inflating your billed input tokens."),
            ("compare-providers", "How do I compare two AI API providers on /compare?", "Run checks on two endpoints (or two models) and paste their /r/{id} links into /compare to see score delta, TTFT, live tok/s, a detector-by-detector diff matrix, and both Pelican SVGs side by side."),
        )),
        _category("openai", "OpenAI / GPT Relay", "OpenAI is checked through behavior, protocol, and fingerprints.", (
            ("openai-proof", "Can Clodex cryptographically prove a GPT model?", "No. OpenAI responses do not include a Claude-like thinking signature. Clodex checks protocol compliance, capability support, and suspicious usage fields."),
            ("openai-fingerprint", "How can GPT -> Claude substitution be detected?", "Anthropic-style fields can leak into OpenAI-shaped responses: input_tokens/output_tokens, usage_source, claude_cache_*, and other adapter traces."),
            ("openai-no-models", "Why are there 0 GPT models?", "The key may be enabled only for a Claude or Gemini group. Preflight shows whether another protocol has models and suggests the right page."),
        )),
        _category("gemini", "Gemini Relay", "Gemini is checked through the OpenAI-compatible endpoint.", (
            ("gemini-path", "Why use the OpenAI-compatible path?", "Most Gemini relays expose /chat/completions compatibility. It lets Clodex check function calling, JSON schema, streaming, and usage consistently."),
            ("gemini-model-not-found", "Why does model_not_found happen often?", "A relay may support only some models, use a different name, or remove a preview model. Preflight helps show available alternatives."),
            ("gemini-official", "Can I check official Google Gemini?", "Yes. Use base_url <code>https://generativelanguage.googleapis.com/v1beta/openai</code> and an AIza... key from Google AI Studio."),
        )),
        _category("privacy", "Privacy And Security", "What happens to API keys and reports.", (
            ("key-stored", "Does Clodex store my API key?", "No. The key is used during the job and is not written to report JSON, logs, or a database. Reports keep only a masked key."),
            ("report-public", "Who can see /r/xxx reports?", "Anyone with the link. Do not share the URL if you are checking a private relay and do not want the result public."),
            ("self-host", "Can I self-host it?", "Yes. The project is open source, so you can run it yourself and keep API keys inside your own network."),
        )),
    ),
    "zh": (
        _category("basics", "relay 基础", "什么是 AI API relay、为什么使用它，以及主要风险。", (
            ("what-is-relay", "什么是 AI API relay?", "它是一个中间 API 服务，接收你的请求并转发到 OpenAI、Anthropic、Google 或其它提供商。好的 relay 像透明代理；差的 relay 可能修改模型、响应字段或 usage。"),
            ("why-use-relay", "为什么使用 relay?", "常见原因包括统一 API、价格、可用性或企业路由。但 relay 会成为可信中间层，因此需要检测。"),
            ("relay-vs-official", "relay 和官方 API 有什么区别?", "官方 API 的字段、错误和计费更稳定。relay 可能 1:1 透传，也可能重新包装响应、隐藏 usage、关闭能力或替换后端。"),
            ("relay-risk", "relay 有哪些风险?", "主要风险是停服、模型替换、计费不准、prompt 被记录，以及 tools、PDF、structured output 等能力缺失。"),
        )),
        _category("authenticity", "模型真伪", "Clodex 如何识别 Claude、GPT、Gemini 是否被替换。", (
            ("verify-authentic", "怎么知道模型是真的?", "Clodex 查看 protocol shape、capability probes 和 usage fingerprints。对于 Claude，还使用 thinking signature 这一最强信号。"),
            ("fake-tactics", "relay 常见作假方式是什么?", "例如卖 GPT 但转发到 Claude；卖 Claude 但通过没有 thinking signature 的 Bedrock-like 层；或关闭高级能力只返回普通文本。"),
            ("ask-who-are-you", "直接问模型是谁可以吗?", "不可靠。身份回答很容易被 system prompt 伪造。协议字段、signature、tool calls 和 usage 更可靠。"),
        )),
        _category("claude", "Claude relay", "Claude 具备服务端加密级 thinking signature，覆盖全部 17 项检测器。", (
            ("thinking-signature", "thinking signature 是什么?", "它是 thinking response 中的 Anthropic 服务端加密签名。relay 理论上无法自己生成，因此缺失或形状异常是强警告信号。"),
            ("claude-coverage", "Claude 检测套件检查什么?", "共 17 项：thinking signature、身份、行为特征、知识、原生 PDF、tool use / 结构化输出、协议规范、流式一致性、message IDs、usage 与 count_tokens、Prompt Caching 缓存、隐藏系统提示词审计、动态 PNG 视觉、防缓存推理、鹈鹕骑车 SVG 与可选 950k 长上下文。"),
            ("claude-cost", "检测会消耗 token 吗?", "会。CLODEX Check 会向你的接口发送真实探针请求，费用由被测接口计费，CLODEX Check 本身完全免费。"),
        )),
        _category("advanced", "鹈鹕测试、缓存、流式测速与并排对比", "进阶真伪审计、真实 tok/s 测速与双报告对比功能说明。", (
            ("pelican-svg", "什么是「鹈鹕骑自行车 SVG」测试？", "这是 Simon Willison 的经典视觉基准：让模型在单次流式请求中用纯 SVG 绘制一只骑自行车的鹈鹕。图形细节与矢量结构让廉价模型替换一目了然。每个模型页面与 /pelican 均有独立标签页。"),
            ("fake-stream", "如何识别「假流式」并测量真实 tok/s？", "流式探针会记录每个分片到达时间（StreamSample），在剔除首字延迟 TTFT 后计算真实生成速度；若代理先整包缓冲再一次性吐出，会被标记为 buffered_burst。"),
            ("prompt-cache-check", "如何验证 Prompt Caching 是否真实生效？", "连续两次发送超过 2000 token 的相同前缀，校验是否真实返回 cache_read_input_tokens > 0（Claude）或 cached_tokens > 0（OpenAI）。"),
            ("system-injection-check", "系统提示词审计能查出什么问题？", "一方面通过随机金丝雀指令确认你的 system prompt 未被覆盖；另一方面通过纯 'hi' 请求排查后台注入隐藏提示词导致的额外计费。"),
            ("compare-providers", "如何在 /compare 并排对比两家中转站？", "分别完成两次检测后，把两份 /r/{id} 链接粘贴到 /compare，即可并排查看总分差值、TTFT、tok/s、逐项检测差异以及两张鹈鹕 SVG。"),
        )),
        _category("openai", "OpenAI / GPT relay", "OpenAI 通过行为、协议和指纹检测。", (
            ("openai-proof", "能加密级证明 GPT 真伪吗?", "不能。OpenAI 响应没有 Claude-like thinking signature。Clodex 检查 protocol compliance、capability support 和可疑 usage 字段。"),
            ("openai-fingerprint", "如何发现 GPT -> Claude 替换?", "Anthropic-style 字段可能漏进 OpenAI-shaped response，例如 input_tokens/output_tokens、usage_source、claude_cache_* 等适配器痕迹。"),
            ("openai-no-models", "为什么 GPT 模型为 0?", "这把 key 可能只开通了 Claude 或 Gemini 组。Preflight 会显示其它协议是否有模型，并建议正确页面。"),
        )),
        _category("gemini", "Gemini relay", "Gemini 通过 OpenAI-compatible endpoint 检测。", (
            ("gemini-path", "为什么使用 OpenAI-compatible path?", "大多数 Gemini relay 暴露 /chat/completions 兼容接口，便于统一检测 function calling、JSON schema、streaming 和 usage。"),
            ("gemini-model-not-found", "为什么经常 model_not_found?", "relay 可能只支持部分模型、使用不同名称或移除 preview 模型。Preflight 会帮助显示可用替代项。"),
            ("gemini-official", "可以检测 Google 官方 Gemini 吗?", "可以。base_url 使用 <code>https://generativelanguage.googleapis.com/v1beta/openai</code>，API key 使用 Google AI Studio 的 AIza... key。"),
        )),
        _category("privacy", "隐私与安全", "API key 和报告如何处理。", (
            ("key-stored", "Clodex 会保存 API key 吗?", "不会。key 只在 job 期间使用，不写入 report JSON、日志或数据库。报告只保留脱敏 key。"),
            ("report-public", "谁能看到 /r/xxx 报告?", "任何拥有链接的人都能看到。如果检测私有 relay 且不想公开结果，请不要分享 URL。"),
            ("self-host", "可以自托管吗?", "可以。项目开源，可以自己运行并让 API key 保持在自己的网络内。"),
        )),
    ),
}


def _build(locale: str) -> tuple[FAQCategory, ...]:
    norm = normalize_locale(locale)
    blocks = _FAQ_DATA.get(norm, _FAQ_DATA["ru"])
    cats: list[FAQCategory] = []
    for cat in blocks:
        entries = tuple(FAQEntry(*entry) for entry in cat["entries"])
        cats.append(FAQCategory(id=str(cat["id"]), title=str(cat["title"]), intro=str(cat["intro"]), entries=entries))
    return tuple(cats)


FAQ_CATEGORIES: tuple[FAQCategory, ...] = _build("ru")


def categories(locale: str = "ru") -> tuple[FAQCategory, ...]:
    return _build(locale)


def total_question_count(locale: str = "ru") -> int:
    return sum(len(c.entries) for c in _build(locale))


def faqpage_jsonld(locale: str = "ru") -> dict:
    cats = _build(locale)
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": entry.q, "acceptedAnswer": {"@type": "Answer", "text": entry.a}}
            for cat in cats
            for entry in cat.entries
        ],
    }


def find_entry(anchor: str, locale: str = "ru") -> tuple[FAQCategory, FAQEntry] | None:
    for cat in _build(locale):
        prefix = cat.id + "-"
        if not anchor.startswith(prefix):
            continue
        entry_id = anchor[len(prefix):]
        for entry in cat.entries:
            if entry.id == entry_id:
                return cat, entry
    return None

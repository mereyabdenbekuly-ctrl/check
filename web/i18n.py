"""Tiny localization helpers for Clodex.

The app uses query param, cookie and Accept-Language to resolve the active
locale. We keep the implementation intentionally small so the public UI,
report strings and CLI output can share the same copy source without pulling
in a full gettext stack.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from starlette.requests import Request


SUPPORTED_LOCALES = ("ru", "en", "zh")
DEFAULT_LOCALE = "ru"

_ALIASES = {
    "zh": "zh",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "cn": "zh",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "ru": "ru",
    "ru-ru": "ru",
}

_LOCALE_NAMES = {"zh": "简体中文", "en": "English", "ru": "Русский"}
_HTML_LANG = {"zh": "zh-CN", "en": "en-US", "ru": "ru-RU"}
_OG_LOCALE = {"zh": "zh_CN", "en": "en_US", "ru": "ru_RU"}


def normalize_locale(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    cleaned = value.strip().lower().replace("_", "-")
    return _ALIASES.get(cleaned, DEFAULT_LOCALE)


def detect_locale(request: Request | None = None, fallback: str | None = None) -> str:
    if request is not None:
        qp = request.query_params.get("lang")
        if qp:
            return normalize_locale(qp)
        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            return normalize_locale(cookie_lang)
    return normalize_locale(fallback)


def lt(locale: str, ru: str, en: str, zh: str | None = None) -> str:
    locale = normalize_locale(locale)
    if locale == "ru":
        return ru
    if locale == "en":
        return en
    return zh if zh is not None else en


def html_lang(locale: str) -> str:
    return _HTML_LANG.get(normalize_locale(locale), _HTML_LANG[DEFAULT_LOCALE])


def og_locale(locale: str) -> str:
    return _OG_LOCALE.get(normalize_locale(locale), _OG_LOCALE[DEFAULT_LOCALE])


def locale_name(locale: str) -> str:
    return _LOCALE_NAMES.get(normalize_locale(locale), _LOCALE_NAMES[DEFAULT_LOCALE])


def with_lang(url: str, locale: str, extra: dict[str, Any] | None = None) -> str:
    locale = normalize_locale(locale)
    parts = urlsplit(str(url))
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if locale == DEFAULT_LOCALE:
        # keep default URLs clean
        query.pop("lang", None)
    else:
        query["lang"] = locale
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            query[key] = str(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@lru_cache(maxsize=None)
def t(locale: str, key: str) -> str:
    locale = normalize_locale(locale)
    return TRANSLATIONS.get(locale, TRANSLATIONS[DEFAULT_LOCALE]).get(
        key,
        TRANSLATIONS[DEFAULT_LOCALE].get(key, key),
    )


def ui(locale: str) -> dict[str, str]:
    locale = normalize_locale(locale)
    out = dict(TRANSLATIONS[DEFAULT_LOCALE])
    out.update(TRANSLATIONS.get(locale, {}))
    out["html_lang"] = html_lang(locale)
    out["og_locale"] = og_locale(locale)
    out["locale_name"] = locale_name(locale)
    return out


_DETECTOR_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "anthropic": {
        "zh": {
            "identity": "身份一致性",
            "behavioral_signature": "行为签名验证",
            "thinking_signature": "思维签名验证",
            "consistency": "模型一致性",
            "knowledge": "知识准确度",
            "pdf": "PDF 文档识别",
            "structured_output": "结构化输出",
            "protocol": "协议规范性",
            "integrity": "响应完整性",
            "token_usage": "Token 用量",
            "message_id": "消息标识规范",
            "prompt_cache": "提示词缓存",
            "system_injection": "系统提示词审计",
            "vision_image": "动态图像视觉",
            "dynamic_challenge": "动态防缓存推理",
            "pelican_svg": "鹈鹕骑车 SVG",
            "long_context": "长上下文真实性",
        },
        "en": {
            "identity": "Identity",
            "behavioral_signature": "Behavioral signature",
            "thinking_signature": "Thinking signature",
            "consistency": "Model consistency",
            "knowledge": "Knowledge",
            "pdf": "PDF recognition",
            "structured_output": "Structured output",
            "protocol": "Protocol",
            "integrity": "Response integrity",
            "token_usage": "Token usage",
            "message_id": "Message ID",
            "prompt_cache": "Prompt caching",
            "system_injection": "System prompt audit",
            "vision_image": "Dynamic PNG vision",
            "dynamic_challenge": "Anti-cache reasoning",
            "pelican_svg": "Pelican SVG test",
            "long_context": "Long context truthfulness",
        },
        "ru": {
            "identity": "Идентичность",
            "behavioral_signature": "Поведенческий отпечаток",
            "thinking_signature": "Отпечаток мышления",
            "consistency": "Согласованность модели",
            "knowledge": "Знания",
            "pdf": "Распознавание PDF",
            "structured_output": "Структурированный вывод",
            "protocol": "Протокол",
            "integrity": "Целостность ответа",
            "token_usage": "Использование токенов",
            "message_id": "ID сообщения",
            "prompt_cache": "Prompt Caching (кэш)",
            "system_injection": "Аудит system-инъекций",
            "vision_image": "Зрение (PNG-код)",
            "dynamic_challenge": "Анти-кэш логика",
            "pelican_svg": "Пеликан-тест (SVG)",
            "long_context": "Проверка длинного контекста",
        },
    },
    "openai": {
        "zh": {
            "basic_request": "基础请求",
            "model_consistency": "模型一致性",
            "function_calling": "函数调用",
            "structured_output": "结构化输出",
            "protocol": "协议规范性",
            "integrity": "流式一致性",
            "token_billing": "Token 计费",
            "tokenizer_probe": "分词器指纹",
            "prompt_cache": "提示词缓存",
            "system_injection": "系统提示词审计",
            "vision_image": "动态图像视觉",
            "dynamic_challenge": "动态防缓存推理",
            "pelican_svg": "鹈鹕骑车 SVG",
            "long_context": "长上下文真实性",
        },
        "en": {
            "basic_request": "Basic request",
            "model_consistency": "Model consistency",
            "function_calling": "Function calling",
            "structured_output": "Structured output",
            "protocol": "Protocol",
            "integrity": "Streaming consistency",
            "token_billing": "Token billing",
            "tokenizer_probe": "Tokenizer probe",
            "prompt_cache": "Prompt caching",
            "system_injection": "System prompt audit",
            "vision_image": "Dynamic PNG vision",
            "dynamic_challenge": "Anti-cache reasoning",
            "pelican_svg": "Pelican SVG test",
            "long_context": "Long context truthfulness",
        },
        "ru": {
            "basic_request": "Базовый запрос",
            "model_consistency": "Согласованность модели",
            "function_calling": "Вызов функций",
            "structured_output": "Структурированный вывод",
            "protocol": "Протокол",
            "integrity": "Согласованность потока",
            "token_billing": "Начисление токенов",
            "tokenizer_probe": "Проба токенизатора",
            "prompt_cache": "Prompt Caching (кэш)",
            "system_injection": "Аудит system-инъекций",
            "vision_image": "Зрение (PNG-код)",
            "dynamic_challenge": "Анти-кэш логика",
            "pelican_svg": "Пеликан-тест (SVG)",
            "long_context": "Проверка длинного контекста",
        },
    },
    "gemini": {
        "zh": {
            "basic_request": "基础请求",
            "model_info": "模型响应形状",
            "function_calling": "函数调用",
            "structured_output": "结构化输出",
            "protocol": "协议规范性",
            "integrity": "流式一致性",
            "token_usage": "Token 用量",
            "tokenizer_probe": "分词器指纹",
            "system_injection": "系统提示词审计",
            "vision_image": "动态图像视觉",
            "dynamic_challenge": "动态防缓存推理",
            "pelican_svg": "鹈鹕骑车 SVG",
        },
        "en": {
            "basic_request": "Basic request",
            "model_info": "Model response shape",
            "function_calling": "Function calling",
            "structured_output": "Structured output",
            "protocol": "Protocol",
            "integrity": "Streaming consistency",
            "token_usage": "Token usage",
            "tokenizer_probe": "Tokenizer probe",
            "system_injection": "System prompt audit",
            "vision_image": "Dynamic PNG vision",
            "dynamic_challenge": "Anti-cache reasoning",
            "pelican_svg": "Pelican SVG test",
        },
        "ru": {
            "basic_request": "Базовый запрос",
            "model_info": "Форма ответа модели",
            "function_calling": "Вызов функций",
            "structured_output": "Структурированный вывод",
            "protocol": "Протокол",
            "integrity": "Согласованность потока",
            "token_usage": "Использование токенов",
            "tokenizer_probe": "Проба токенизатора",
            "system_injection": "Аудит system-инъекций",
            "vision_image": "Зрение (PNG-код)",
            "dynamic_challenge": "Анти-кэш логика",
            "pelican_svg": "Пеликан-тест (SVG)",
        },
    },
}


def detector_display(locale: str, protocol: str) -> list[tuple[str, str]]:
    locale = normalize_locale(locale)
    protocol = protocol if protocol in _DETECTOR_LABELS else "anthropic"
    labels = _DETECTOR_LABELS[protocol].get(locale) or _DETECTOR_LABELS[protocol][DEFAULT_LOCALE]
    order = []
    for key in _DETECTOR_LABELS[protocol][DEFAULT_LOCALE].keys():
        order.append((key, labels.get(key, key)))
    return order


def detector_labels_map(locale: str, protocol: str) -> dict[str, str]:
    return dict(detector_display(locale, protocol))


_DETECTOR_CRITERIA: dict[str, dict[str, dict[str, str]]] = {
    "anthropic": {
        "ru": {
            "identity": "Прямой запрос самоидентификации без системного промпта: ищет признаки Claude/Anthropic и упоминания сторонних брендов.",
            "behavioral_signature": "3 контрольных промпта на характерный стиль Claude: Markdown-выделение, структурированные списки и тон отказа.",
            "thinking_signature": "Включает adaptive/extended thinking и проверяет криптографическую серверную подпись Anthropic (signature 500–2000 байт).",
            "consistency": "Сверяет response.model с запрошенной моделью и измеряет стабильность длины ответов на 3 одинаковых запусках.",
            "knowledge": "5 фактологических вопросов об Anthropic и Claude (руководство, Constitutional AI, год релиза, штаб-квартира).",
            "pdf": "Отправляет сгенерированный PDF-документ с уникальным кодом MAGIC-... и проверяет нативное чтение PDF-вложений.",
            "structured_output": "Запрашивает вызов инструмента get_weather: проверяет блок tool_use, префикс toolu_, JSON-схему и stop_reason=tool_use.",
            "integrity": "Сравнивает stream (SSE) и non-stream на одном промпте: совпадение текста, char/token, stop_reason и входные/выходные токены.",
            "token_usage": "Проверяет наличие usage, прирост input_tokens на длинном тексте, stream vs non-stream и сверку с /v1/messages/count_tokens.",
            "protocol": "Пассивный аудит всех ответов: соответствие формату Anthropic Messages API и отсутствие артефактов чужих провайдеров.",
            "message_id": "Пассивная проверка префиксов и структуры идентификаторов сообщений (msg_...) во всех полученных ответах.",
            "prompt_cache": "2 последовательных запроса с общим блоком ~2200 токенов и cache_control=ephemeral: проверяет запись и реальное попадание в кэш (cache_read > 0).",
            "system_injection": "Канареечный тест сохранности пользовательского system prompt и замер скрытого оверхеда входных токенов на голом «hi».",
            "vision_image": "Генерирует свежий PNG в памяти со случайным кодом VRF-XXXX (нельзя закэшировать) и проверяет реальное мультимодальное зрение модели.",
            "dynamic_challenge": "Генерирует одноразовую задачу (арифметика + посимвольный разворот случайного слова в JSON), отсекающую кэш-прокси и слабые модели.",
            "pelican_svg": "Визуальный тест Симона Уиллисона: потоковая генерация SVG «пеликан на велосипеде» + замер реальной скорости tok/s и анализ геометрии.",
            "long_context": "Опциональный тест «иголка в стоге сена» на длинном контексте (32k–1M токенов) для выявления скрытого урезания окна.",
        },
        "en": {
            "identity": "Direct self-identification probe without a system prompt: checks for Claude/Anthropic signals and non-Anthropic brand leaks.",
            "behavioral_signature": "3 behavioral probes checking characteristic Claude Markdown formatting, numbered lists, and constructive refusal tone.",
            "thinking_signature": "Enables adaptive/extended thinking and verifies the unforgeable Anthropic server-side cryptographic signature (500–2000 B).",
            "consistency": "Matches response.model against the requested model and checks output-token stability across 3 identical runs.",
            "knowledge": "5 factual questions about Anthropic & Claude (leadership, Constitutional AI, launch year, headquarters).",
            "pdf": "Sends a dynamically generated PDF containing a unique MAGIC-... token to verify native PDF document vision.",
            "structured_output": "Calls get_weather tool: validates tool_use block, toolu_ ID prefix, JSON schema compliance, and stop_reason=tool_use.",
            "integrity": "Compares streaming (SSE) vs non-streaming on an identical prompt: text similarity, char/token ratio, stop_reason, and token counts.",
            "token_usage": "Checks usage presence, input_tokens growth on a longer prompt, stream vs non-stream parity, and /v1/messages/count_tokens alignment.",
            "protocol": "Passive audit across all captured responses for Anthropic Messages JSON schema fidelity and foreign-provider artifacts.",
            "message_id": "Passive check of message ID prefixes (msg_...) and format consistency across all responses.",
            "prompt_cache": "2 back-to-back calls with a ~2,200-token ephemeral cached prefix: verifies real cache write and cache_read_input_tokens > 0.",
            "system_injection": "Canary test verifying your system prompt reaches the model intact plus hidden input-token bloat audit on a bare 'hi'.",
            "vision_image": "Renders a fresh in-memory PNG with a random VRF-XXXX code (impossible to pre-cache) to verify true multimodal vision support.",
            "dynamic_challenge": "Fresh per-run arithmetic + character-by-character string reversal in strict JSON to expose canned proxies and weak models.",
            "pelican_svg": "Simon Willison's visual SVG benchmark ('pelican riding a bicycle') streamed live to measure real tok/s and vector complexity.",
            "long_context": "Optional needle-in-a-haystack test across 32k–1M context to detect hidden context window truncation.",
        },
        "zh": {
            "identity": "无 system prompt 直接询问身份，检测是否包含 Claude/Anthropic 信号及第三方品牌泄露。",
            "behavioral_signature": "3 组行为特征探针：检测 Claude 典型的 Markdown 粗体、编号列表与拒答语气。",
            "thinking_signature": "开启 adaptive/extended thinking，校验无法伪造的 Anthropic 服务端加密 thinking signature（500–2000 字节）。",
            "consistency": "核对 response.model 字段是否匹配，并通过 3 次相同请求检测输出 token 长度稳定性。",
            "knowledge": "5 道关于 Anthropic 与 Claude 的基础事实题（管理层、Constitutional AI、发布年份、总部）。",
            "pdf": "发送包含随机 MAGIC-... 标记的动态 PDF 文档，验证原生 PDF 解析能力。",
            "structured_output": "触发 get_weather 工具调用：校验 tool_use 块、toolu_ 前缀、参数 JSON Schema 与 stop_reason=tool_use。",
            "integrity": "对比同一提示词的流式 (SSE) 与非流式响应：文本相似度、char/token、stop_reason 及输入/输出 token 一致性。",
            "token_usage": "检测 usage 完整性、长短文本 input_tokens 增量、流式与非流式对齐及 /v1/messages/count_tokens 交叉核验。",
            "protocol": "被动审计全部响应，检查是否符合 Anthropic Messages API 协议规范且无异构转换痕迹。",
            "message_id": "被动检查所有响应中的消息 ID 前缀 (msg_...) 及格式一致性。",
            "prompt_cache": "连续两次发送约 2200 token 的 ephemeral 缓存前缀，验证真实缓存写入与二次命中 (cache_read > 0)。",
            "system_injection": "通过随机金丝雀指令验证 system prompt 未被覆盖，并检测纯 'hi' 请求是否存在隐藏输入 token 膨胀。",
            "vision_image": "每次检测实时在内存中渲染带随机 VRF-XXXX 验证码的 PNG 图片（无法预缓存），验证原生多模态视觉能力。",
            "dynamic_challenge": "每次随机生成算术计算 + 字符串逐字反转 JSON 题目，识破固定响应缓存代理与弱模型降级。",
            "pelican_svg": "Simon Willison 视觉基准：流式生成「鹈鹕骑自行车」SVG，同时实测真实流式 tok/s 与矢量复杂度。",
            "long_context": "可选长上下文大海捞针测试（32k–1M），检测是否存在隐藏上下文截断。",
        },
    },
    "openai": {
        "ru": {
            "basic_request": "Базовая доступность Chat Completions: проверяет статус ответа, choices, finish_reason и текстовый контент.",
            "model_consistency": "Сверяет response.model с запрошенной моделью и стабильность ответа на повторных запусках.",
            "function_calling": "Проверяет корректный вызов tool/function: tool_calls, call_id, JSON-аргументы и finish_reason=tool_calls.",
            "structured_output": "Проверяет строгий json_schema (response_format) на точное соблюдение полей, типов и отсутствие лишнего текста.",
            "protocol": "Пассивный аудит структуры OpenAI Chat Completions / Responses и поиск артефактов подмены бэкенда (Claude/Gemini).",
            "integrity": "Сравнивает потоковый (SSE) и обычный ответы: совпадение текста, usage в финальном чанке и finish_reason.",
            "token_billing": "Проверяет наличие usage, прирост prompt_tokens на длинном тексте и согласованность stream vs non-stream.",
            "tokenizer_probe": "Проба токенизатора (o200k_base): мультибайтные символы, кириллица, CJK, emoji и склейка цифр/пробелов для выявления подмены.",
            "prompt_cache": "2 последовательных запроса с общим системным префиксом >1024 токенов: проверяет реальное кэширование cached_tokens.",
            "system_injection": "Канареечный тест сохранности пользовательского system prompt и аудит скрытого раздувания prompt_tokens на «hi».",
            "vision_image": "Генерирует свежий PNG в памяти со случайным кодом VRF-XXXX (нельзя закэшировать) и проверяет реальное мультимодальное зрение модели.",
            "dynamic_challenge": "Генерирует одноразовую задачу (арифметика + посимвольный разворот случайного слова в JSON), отсекающую кэш-прокси и слабые модели.",
            "pelican_svg": "Визуальный тест «пеликан на велосипеде» (SVG в потоке): оценивает векторную геометрию и реальную скорость tok/s.",
            "long_context": "Опциональный тест «иголка в стоге сена» на большом контексте для проверки реального размера окна.",
        },
        "en": {
            "basic_request": "Basic Chat Completions sanity: validates status, choices array, finish_reason, and response text.",
            "model_consistency": "Verifies response.model alignment and answer stability across repeated runs.",
            "function_calling": "Tests tool/function calling: validates tool_calls array, IDs, JSON arguments, and finish_reason=tool_calls.",
            "structured_output": "Tests strict json_schema response_format for exact keys, types, and zero extra prose.",
            "protocol": "Passive audit of OpenAI Chat Completions schema shape and cross-provider substitution artifacts.",
            "integrity": "Compares streaming (SSE) vs non-streaming parity: text similarity, final stream usage, and finish_reason.",
            "token_billing": "Checks usage fields, prompt_tokens delta on longer input, and stream vs non-stream token parity.",
            "tokenizer_probe": "o200k_base BPE edge-case probe (multibyte Unicode, emoji, digit/whitespace merging) to expose mismatched tokenizers.",
            "prompt_cache": "2 sequential calls with a >1,024-token system prefix verifying automatic prompt caching (cached_tokens > 0).",
            "system_injection": "Canary test verifying your system prompt is not stripped/overridden plus hidden prompt_tokens bloat audit on 'hi'.",
            "vision_image": "Renders a fresh in-memory PNG with a random VRF-XXXX code (impossible to pre-cache) to verify true multimodal vision support.",
            "dynamic_challenge": "Fresh per-run arithmetic + character-by-character string reversal in strict JSON to expose canned proxies and weak models.",
            "pelican_svg": "Streamed SVG visual benchmark ('pelican riding a bicycle') measuring real tok/s throughput and vector complexity.",
            "long_context": "Optional needle-in-a-haystack long-context probe to catch silent context truncation.",
        },
        "zh": {
            "basic_request": "基础 Chat Completions 可用性检测：校验响应状态、choices、finish_reason 与正文。",
            "model_consistency": "核对 response.model 字段匹配度及多次重复请求的输出稳定性。",
            "function_calling": "测试函数/工具调用：校验 tool_calls、ID、JSON 参数及 finish_reason=tool_calls。",
            "structured_output": "测试严格 json_schema 结构化输出，验证字段类型与纯 JSON 格式。",
            "protocol": "被动审计全部响应结构是否符合 OpenAI 规范，排查 Claude/Gemini 伪装痕迹。",
            "integrity": "对比流式 (SSE) 与非流式输出：文本一致性、流尾 usage 及 finish_reason。",
            "token_billing": "检查 usage 字段、长短输入 prompt_tokens 增量与流式/非流式计费一致性。",
            "tokenizer_probe": "o200k_base 分词器边界测试（多字节字符、Emoji、数字与空白合并），识别底层异构分词器。",
            "prompt_cache": "连续两次发送超 1024 token 前缀，校验 prompt_tokens_details.cached_tokens 是否真实命中缓存。",
            "system_injection": "随机金丝雀验证 system prompt 未被篡改，并检测纯 'hi' 请求的隐蔽输入 token 注入。",
            "vision_image": "实时在内存中渲染带随机 VRF-XXXX 验证码的 PNG 图片（无法预缓存），验证原生多模态视觉能力。",
            "dynamic_challenge": "每次随机生成算术计算 + 字符串逐字反转 JSON 题目，识破固定响应缓存代理与弱模型降级。",
            "pelican_svg": "流式生成「鹈鹕骑自行车」SVG 视觉测试，同步测量真实流式 tok/s 与图形精细度。",
            "long_context": "可选长上下文大海捞针测试，排查隐蔽上下文截断。",
        },
    },
    "gemini": {
        "ru": {
            "basic_request": "Базовый запрос к Gemini через OpenAI-совместимый эндпоинт: проверка ответа, choices и finish_reason.",
            "model_info": "Проверяет форму объекта ответа и соответствие поля model заявленной модели Gemini.",
            "function_calling": "Проверяет function calling: корректные tool_calls, валидные JSON-аргументы и finish_reason.",
            "structured_output": "Проверяет строгий JSON Schema вывод без лишней разметки и нарушений схемы.",
            "protocol": "Пассивный аудит всех ответов на соответствие OpenAI-совместимому контракту без битых полей.",
            "integrity": "Сравнивает SSE-поток и обычный ответ: совпадение текста, токены и корректный конец потока.",
            "token_usage": "Проверяет полноту usage, прирост prompt_tokens на длинном промпте и согласованность со стримом.",
            "tokenizer_probe": "Проба токенизатора (SentencePiece): мультибайтные символы, кириллица, CJK, emoji и склейка цифр/пробелов.",
            "system_injection": "Канареечный тест сохранности пользовательского system prompt и аудит скрытого раздувания prompt_tokens на «hi».",
            "vision_image": "Генерирует свежий PNG в памяти со случайным кодом VRF-XXXX (нельзя закэшировать) и проверяет реальное мультимодальное зрение модели.",
            "dynamic_challenge": "Генерирует одноразовую задачу (арифметика + посимвольный разворот случайного слова в JSON), отсекающую кэш-прокси и слабые модели.",
            "pelican_svg": "Визуальный тест «пеликан на велосипеде» (SVG в потоке): оценивает векторную геометрию и реальную скорость tok/s.",
        },
        "en": {
            "basic_request": "Basic Gemini probe via OpenAI-compatible endpoint: checks response shape, choices, and finish_reason.",
            "model_info": "Verifies response envelope shape and model field alignment with the requested Gemini model.",
            "function_calling": "Validates function calling: tool_calls structure, valid JSON arguments, and finish_reason.",
            "structured_output": "Validates strict JSON Schema output without extra prose or schema violations.",
            "protocol": "Passive audit across all captured responses for clean OpenAI-compatible protocol compliance.",
            "integrity": "Compares streaming (SSE) vs non-streaming output parity, token counts, and stream completion.",
            "token_usage": "Checks usage presence, prompt_tokens growth on longer input, and stream vs non-stream alignment.",
            "tokenizer_probe": "SentencePiece tokenizer edge-case probe (multibyte Unicode, emoji, digit/whitespace merging).",
            "system_injection": "Canary test verifying your system prompt reaches the model intact plus hidden input-token bloat audit on 'hi'.",
            "vision_image": "Renders a fresh in-memory PNG with a random VRF-XXXX code (impossible to pre-cache) to verify true multimodal vision support.",
            "dynamic_challenge": "Fresh per-run arithmetic + character-by-character string reversal in strict JSON to expose canned proxies and weak models.",
            "pelican_svg": "Streamed SVG visual benchmark ('pelican riding a bicycle') measuring real tok/s throughput and vector complexity.",
        },
        "zh": {
            "basic_request": "通过 OpenAI 兼容接口发送基础请求，校验 Gemini 响应可用性、choices 与 finish_reason。",
            "model_info": "检查响应对象结构及 model 字段与目标 Gemini 模型的一致性。",
            "function_calling": "测试函数调用：校验 tool_calls 结构、JSON 参数和 finish_reason。",
            "structured_output": "测试严格 JSON Schema 输出是否符合预期字段与类型。",
            "protocol": "被动审计全部响应的 OpenAI 兼容协议规范性。",
            "integrity": "对比流式 (SSE) 与非流式输出文本、usage 与流结束标记。",
            "token_usage": "验证 usage 字段完整性、长短输入 token 增量与流式/非流式一致性。",
            "tokenizer_probe": "SentencePiece 分词器边界探针（多字节字符、Emoji、数字与空白合并）。",
            "system_injection": "随机金丝雀验证 system prompt 未被覆盖，并检测纯 'hi' 请求的隐藏输入 token 注入。",
            "vision_image": "实时在内存中渲染带随机 VRF-XXXX 验证码的 PNG 图片（无法预缓存），验证原生多模态视觉能力。",
            "dynamic_challenge": "每次随机生成算术计算 + 字符串逐字反转 JSON 题目，识破固定响应缓存代理与弱模型降级。",
            "pelican_svg": "流式生成「鹈鹕骑自行车」SVG 视觉测试，同步测量真实流式 tok/s 与图形复杂度。",
        },
    },
}


def detector_criteria(locale: str, protocol: str) -> dict[str, str]:
    locale = normalize_locale(locale)
    protocol = protocol if protocol in _DETECTOR_CRITERIA else "anthropic"
    return dict(
        _DETECTOR_CRITERIA[protocol].get(locale)
        or _DETECTOR_CRITERIA[protocol][DEFAULT_LOCALE]
    )


_STATUS_SHORT = {
    "zh": {"pass": "通过", "skip": "跳过", "error": "异常", "warn": "警告", "fail": "未通过", "unknown": "无法判断"},
    "en": {"pass": "Pass", "skip": "Skip", "error": "Error", "warn": "Warn", "fail": "Fail", "unknown": "N/A"},
    "ru": {"pass": "OK", "skip": "Пропуск", "error": "Ошибка", "warn": "Риск", "fail": "Не пройдено", "unknown": "Неизвестно"},
}


def status_short(locale: str, status: str, name: str | None = None) -> str:
    locale = normalize_locale(locale)
    status = status or "skip"
    if status == "skip" and name in {"token_billing", "token_usage"}:
        return _STATUS_SHORT[locale]["unknown"]
    if status == "skip" and name == "long_context":
        return {"zh": "未启用", "en": "Off", "ru": "Выкл"}.get(locale, "Off")
    return _STATUS_SHORT[locale].get(status, _STATUS_SHORT[locale]["unknown"])


_VERDICT_LABELS_BY_LOCALE: dict[str, dict[str, str]] = {
    "ru": {"passed": "Пройдено", "marginal": "Есть риски", "failed": "Не пройдено"},
    "en": {"passed": "Passed", "marginal": "At risk", "failed": "Failed"},
    "zh": {"passed": "通过", "marginal": "存在风险", "failed": "未达标"},
}


def verdict_labels_for_locale(locale: str) -> dict[str, str]:
    loc = normalize_locale(locale)
    return dict(_VERDICT_LABELS_BY_LOCALE.get(loc, _VERDICT_LABELS_BY_LOCALE[DEFAULT_LOCALE]))


def tier_banner_for_locale(locale: str, protocol: str) -> tuple[str, str]:
    loc = normalize_locale(locale)
    proto = (protocol or "anthropic").lower()
    if proto == "openai":
        return (
            lt(loc, "Поведенческий и протокольный уровень", "Behavior & protocol level", "行为/协议级验证"),
            lt(
                loc,
                "OpenAI не отдаёт серверную криптоподпись уровня Claude. Проверка анализирует соответствие Chat Completions API, поддержку tools и structured output, поток и usage-отпечатки сторонних адаптеров.",
                "OpenAI responses do not expose a Claude-like cryptographic signature. This check inspects Chat Completions compliance, tool & structured output support, streaming parity, and third-party adapter fingerprints in usage.",
                "OpenAI 响应不包含 Claude 级别的加密签名。本检测重点检查 Chat Completions 协议规范、工具调用与结构化输出能力、流式一致性以及 usage 字段中的跨厂商适配痕迹。",
            ),
        )
    if proto == "gemini":
        return (
            lt(loc, "Протокольный уровень", "Protocol level", "协议级验证"),
            lt(
                loc,
                "Проверка тестирует Gemini через OpenAI-совместимый путь POST /chat/completions: структуру ответа, function calling, JSON Schema, стриминг и согласованность usage.",
                "This check probes Gemini through the OpenAI-compatible POST /chat/completions path: response shape, function calling, JSON Schema, streaming parity, and usage consistency.",
                "本检测通过 OpenAI 兼容路径 POST /chat/completions 探测 Gemini relay，验证响应结构、函数调用、JSON Schema、流式一致性与 usage 字段。",
            ),
        )
    return (
        lt(loc, "Криптографический уровень", "Cryptographic level", "加密级验证"),
        lt(
            loc,
            "Claude thinking signature подписывается на стороне серверов Anthropic. Успешное прохождение этой проверки — самый надёжный сигнал оригинальной модели Claude.",
            "Claude thinking signatures are signed server-side by Anthropic. Passing this check is the strongest authenticity signal in the suite.",
            "Claude thinking signature 由 Anthropic 服务端签发，通过该项是目前检测集中可信度最高的原版模型真伪信号。",
        ),
    )


def result_caption(locale: str, score: float, verdict: str, protocol: str = "anthropic") -> str:
    locale = normalize_locale(locale)
    if locale == "zh":
        if verdict == "passed" and score >= 95 and protocol == "anthropic":
            return "完全一致"
        if verdict == "passed" and score >= 85:
            return "协议表现良好" if protocol in {"openai", "gemini"} else "优秀"
        if verdict == "passed":
            return "基本通过" if protocol in {"openai", "gemini"} else "通过"
        if verdict == "marginal":
            return "存在风险" if protocol in {"openai", "gemini"} else "基本合格"
        return "未达标"
    if locale == "en":
        if verdict == "passed" and score >= 95 and protocol == "anthropic":
            return "Exact match"
        if verdict == "passed" and score >= 85:
            return "Protocol looks good" if protocol in {"openai", "gemini"} else "Excellent"
        if verdict == "passed":
            return "Mostly passed" if protocol in {"openai", "gemini"} else "Passed"
        if verdict == "marginal":
            return "At risk" if protocol in {"openai", "gemini"} else "Mostly valid"
        return "Failed"
    if verdict == "passed" and score >= 95 and protocol == "anthropic":
        return "Полное совпадение"
    if verdict == "passed" and score >= 85:
        return "Протокол выглядит хорошо" if protocol in {"openai", "gemini"} else "Отлично"
    if verdict == "passed":
        return "Почти пройдено" if protocol in {"openai", "gemini"} else "Пройдено"
    if verdict == "marginal":
        return "Есть риск" if protocol in {"openai", "gemini"} else "Условно ок"
    return "Не пройдено"


TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        "site_name": "Clodex",
        "site_tagline": "AI API relay authenticity checker",
        "nav_home": "首页",
        "nav_claude": "Claude",
        "nav_openai": "OpenAI",
        "nav_gemini": "Gemini",
        "nav_compare": "对比",
        "nav_leaderboard": "红黑榜",
        "nav_faq": "常见问题",
        "footer_projects": "项目",
        "footer_tools": "工具",
        "footer_resources": "资源",
        "footer_desc": "协议字段 + 加密签名 + 长上下文 needle-in-haystack 三层验证。代码完全开源,API key 永不落盘。",
        "footer_tagline": "AI API relay authenticity checker",
        "footer_license": "License (AGPL-3.0)",
        "footer_security": "安全策略",
        "footer_contrib": "贡献指南",
        "footer_source": "GitHub 源码",
        "footer_rank": "检测历史排行",
        "footer_faq": "常见问题",
        "footer_copy": "独立测评 · 字段级穿透 · AGPL-3.0 开源 · 代码可逐行审计",
        "meta_reports": "{reports} 份报告覆盖 {relays} 家relay。",
        "meta_bayesian": "贝叶斯加权排行。",
        "leaderboard_single_sample": "单次样本,仅供参考",
        "leaderboard_common_issues": "常见问题:",
        "leaderboard_median": "中位",
        "leaderboard_date": "日期",
        "leaderboard_protocol": "协议",
        "leaderboard_model": "模型",
        "leaderboard_score": "分数",
        "leaderboard_verdict": "判定",
        "leaderboard_fails": "失败",
        "leaderboard_report": "报告",
        "leaderboard_no_answer": "没找到答案?",
        "faq_toc": "目录",
        "faq_no_answer_body": "欢迎在 GitHub 提 issue,或者直接跑一次检测看实际结果 — 报告 details 里包含具体的扣分原因,通常自带答案。",
        "running_loading_report": "检测完成,正在加载报告…",
        "running_failed": "检测失败",
        "running_running": "正在检测中…",
        "running_queued": "排队中…",
        "running_unknown_error": "未知错误",
        "running_poll_failed": "轮询失败",
        "coming_email_label": "邮箱",
        "coming_email_placeholder": "you@example.com",
        "coming_submit_failed": "提交失败",
        "menu_open": "打开菜单",
        "menu_close": "关闭菜单",
        "copy_button": "已复制!",
        "share_button": "分享",
        "download_jpg": "下载 JPG",
        "lang_switch": "语言",
        "probe_failed": "探测失败,但不影响检测继续",
        "probe_rate_limited": "探测过于频繁,稍后再试",
        "detection_continues": "检测仍可继续",
        "auth_failed": "鉴权失败",
        "models_unavailable": "该relay不暴露 /v1/models",
        "switch_protocol": "改用 {label} 协议",
        "available_models": "个可用模型",
        "handoff_from": "已从 {label} 页面带入凭据",
        "reprobe": "正在重新探测",
        "page_loading": "正在加载…",

        "relay_fallback": "relay",
        "seo_report_title": "{domain} {protocol} relay检测: {score:.0f}/100 {verdict} | CLODEX Check",
        "seo_report_title_model": "{domain} {protocol} {model} 检测: {score:.0f}/100 {verdict} | CLODEX Check",
        "seo_report_description": "{domain} 的 {protocol} relay 检测完整报告：模型 {model}，总分 {score:.0f}/100，结论 {verdict}。{total} 项检测中 {passed} 项通过，{failed} 项未通过。CLODEX Check 从字段级检查 relay 的真实性和质量。",
        "seo_report_og": "{domain} 报告：{score:.0f}/100 {verdict}（{passed}/{total} 通过）",
        "faq_title": "常见问题",
        "faq_intro": "Clodex 帮你判断 AI API relay是否真的透传 Claude、OpenAI 或 Gemini。",
        "result_title": "检测结果",
        "running_title": "检测进行中",
        "share": "分享",
        "download": "下载 JPG",
        "back_home": "返回首页",
        "leaderboard_title": "relay红黑榜",
        "leaderboard_detail": "relay详情",
        "hub_title": "AI API relay authenticity checker",
    },
    "en": {
        "site_name": "Clodex",
        "site_tagline": "AI API relay authenticity checker",
        "nav_home": "Home",
        "nav_claude": "Claude",
        "nav_openai": "OpenAI",
        "nav_gemini": "Gemini",
        "nav_compare": "Compare",
        "nav_leaderboard": "Leaderboard",
        "nav_faq": "FAQ",
        "footer_projects": "Project",
        "footer_tools": "Tools",
        "footer_resources": "Resources",
        "footer_desc": "Protocol fields + cryptographic signatures + long-context needle-in-haystack checks. Fully open source; API keys are never written to disk.",
        "footer_tagline": "AI API relay authenticity checker",
        "footer_license": "License (AGPL-3.0)",
        "footer_security": "Security",
        "footer_contrib": "Contributing",
        "footer_source": "GitHub source",
        "footer_rank": "Detection history",
        "footer_faq": "FAQ",
        "footer_copy": "Independent checks · field-level inspection · AGPL-3.0 open source · auditable line by line",
        "meta_reports": "{reports} reports across {relays} relays.",
        "meta_bayesian": "Bayesian ranking.",
        "leaderboard_single_sample": "Single sample, for reference only",
        "leaderboard_common_issues": "Common issues:",
        "leaderboard_median": "Median",
        "leaderboard_date": "Date",
        "leaderboard_protocol": "Protocol",
        "leaderboard_model": "Model",
        "leaderboard_score": "Score",
        "leaderboard_verdict": "Verdict",
        "leaderboard_fails": "Fails",
        "leaderboard_report": "Report",
        "leaderboard_no_answer": "Didn't find an answer?",
        "faq_toc": "Contents",
        "faq_no_answer_body": "Open a GitHub issue or run a check to see the real result — the report details usually tell you why.",
        "running_loading_report": "Done, loading report…",
        "running_failed": "Detection failed",
        "running_running": "Detecting…",
        "running_queued": "Queued…",
        "running_unknown_error": "Unknown error",
        "running_poll_failed": "Polling failed",
        "coming_email_label": "Email",
        "coming_email_placeholder": "you@example.com",
        "coming_submit_failed": "Submission failed",
        "menu_open": "Open menu",
        "menu_close": "Close menu",
        "copy_button": "Copied!",
        "share_button": "Share",
        "download_jpg": "Download JPG",
        "lang_switch": "Language",
        "page_loading": "Loading…",
        "probe_failed": "Probe failed, but detection can continue",
        "probe_rate_limited": "Probe rate limited, try again later",
        "detection_continues": "detection can continue",
        "auth_failed": "Authentication failed",
        "models_unavailable": "This relay does not expose /v1/models",
        "switch_protocol": "Switch to {label} protocol",
        "available_models": "available models",
        "handoff_from": "Loaded credentials from {label} page",
        "reprobe": "reprobing",
        "relay_fallback": "relay",
        "seo_report_title": "{domain} {protocol} relay check: {score:.0f}/100 {verdict} | CLODEX Check",
        "seo_report_title_model": "{domain} {protocol} {model} check: {score:.0f}/100 {verdict} | CLODEX Check",
        "seo_report_description": "Full report for the {protocol} relay check on {domain}: model {model}, total score {score:.0f}/100, verdict {verdict}. {passed} of {total} checks passed and {failed} failed. CLODEX Check inspects the relay at field level to reveal authenticity and quality.",
        "seo_report_og": "{domain} report: {score:.0f}/100 {verdict} ({passed}/{total} passed)",
        "faq_title": "FAQ",
        "faq_intro": "Clodex helps detect whether an AI API relay is truly passing through Claude, OpenAI or Gemini.",
        "result_title": "Detection result",
        "running_title": "Detection in progress",
        "share": "Share",
        "download": "Download JPG",
        "back_home": "Back to home",
        "leaderboard_title": "Relay leaderboard",
        "leaderboard_detail": "Relay detail",
        "hub_title": "AI API relay authenticity checker",
    },
    "ru": {
        "site_name": "Clodex",
        "site_tagline": "Проверка подлинности AI API relay",
        "nav_home": "Главная",
        "nav_claude": "Claude",
        "nav_openai": "OpenAI",
        "nav_gemini": "Gemini",
        "nav_compare": "Сравнение",
        "nav_leaderboard": "Рейтинг",
        "nav_faq": "FAQ",
        "footer_projects": "Проект",
        "footer_tools": "Инструменты",
        "footer_resources": "Ресурсы",
        "footer_desc": "Проверка полей протокола + криптографических подписей + long-context needle-in-haystack. Код полностью открыт, API-ключи никогда не пишутся на диск.",
        "footer_tagline": "Проверка подлинности AI API relay",
        "footer_license": "License (AGPL-3.0)",
        "footer_security": "Безопасность",
        "footer_contrib": "Участие",
        "footer_source": "Исходники GitHub",
        "footer_rank": "История проверок",
        "footer_faq": "FAQ",
        "footer_copy": "Независимая проверка · инспекция на уровне полей · AGPL-3.0 open source · можно проверить построчно",
        "meta_reports": "{reports} отчётов по {relays} релеям.",
        "meta_bayesian": "Байесовский рейтинг.",
        "leaderboard_single_sample": "Один пример, только для справки",
        "leaderboard_common_issues": "Частые проблемы:",
        "leaderboard_median": "Медиана",
        "leaderboard_date": "Дата",
        "leaderboard_protocol": "Протокол",
        "leaderboard_model": "Модель",
        "leaderboard_score": "Счёт",
        "leaderboard_verdict": "Вердикт",
        "leaderboard_fails": "Ошибки",
        "leaderboard_report": "Отчёт",
        "leaderboard_no_answer": "Не нашли ответ?",
        "faq_toc": "Содержание",
        "faq_no_answer_body": "Откройте issue на GitHub или запустите проверку, чтобы увидеть реальный результат — обычно отчёт сам объясняет, что пошло не так.",
        "running_loading_report": "Готово, загружаем отчёт…",
        "running_failed": "Проверка не удалась",
        "running_running": "Проверяем…",
        "running_queued": "В очереди…",
        "running_unknown_error": "Неизвестная ошибка",
        "running_poll_failed": "Сбой опроса",
        "coming_email_label": "Email",
        "coming_email_placeholder": "you@example.com",
        "coming_submit_failed": "Ошибка отправки",
        "menu_open": "Открыть меню",
        "menu_close": "Закрыть меню",
        "copy_button": "Скопировано!",
        "share_button": "Поделиться",
        "download_jpg": "Скачать JPG",
        "lang_switch": "Язык",
        "page_loading": "Загрузка…",
        "probe_failed": "Проверка не удалась, но проверку можно продолжить",
        "probe_rate_limited": "Слишком много проверок, попробуйте позже",
        "detection_continues": "проверка может продолжаться",
        "auth_failed": "Ошибка авторизации",
        "models_unavailable": "Этот relay не отдаёт /v1/models",
        "switch_protocol": "Переключиться на протокол {label}",
        "available_models": "доступных моделей",
        "handoff_from": "Подхвачены данные со страницы {label}",
        "reprobe": "повторная проверка",
        "relay_fallback": "relay",
        "seo_report_title": "{domain}: проверка {protocol} relay — {score:.0f}/100 ({verdict}) | CLODEX Check",
        "seo_report_title_model": "{domain}: проверка {protocol} {model} — {score:.0f}/100 ({verdict}) | CLODEX Check",
        "seo_report_description": "Полный отчёт проверки {protocol} relay для {domain}: модель {model}, итоговый счёт {score:.0f}/100, вердикт {verdict}. Пройдено {passed} из {total} проверок, ошибок: {failed}. CLODEX Check проверяет relay на уровне полей, чтобы показать подлинность и качество.",
        "seo_report_og": "{domain}: отчёт проверки {score:.0f}/100 {verdict}, пройдено {passed}/{total}",
        "faq_title": "FAQ",
        "faq_intro": "Clodex помогает понять, действительно ли AI API relay передаёт Claude, OpenAI или Gemini.",
        "result_title": "Результат проверки",
        "running_title": "Проверка идёт",
        "share": "Поделиться",
        "download": "Скачать JPG",
        "back_home": "На главную",
        "leaderboard_title": "Рейтинг релеев",
        "leaderboard_detail": "Детали релея",
        "hub_title": "Проверка подлинности AI API relay",
    },
}

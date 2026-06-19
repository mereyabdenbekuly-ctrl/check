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
        },
        "en": {
            "basic_request": "Basic request",
            "model_info": "Model response shape",
            "function_calling": "Function calling",
            "structured_output": "Structured output",
            "protocol": "Protocol",
            "integrity": "Streaming consistency",
            "token_usage": "Token usage",
        },
        "ru": {
            "basic_request": "Базовый запрос",
            "model_info": "Форма ответа модели",
            "function_calling": "Вызов функций",
            "structured_output": "Структурированный вывод",
            "protocol": "Протокол",
            "integrity": "Согласованность потока",
            "token_usage": "Использование токенов",
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
        "seo_report_title": "{domain} {protocol} relay检测: {score:.0f}/100 {verdict} | Clodex",
        "seo_report_description": "{domain} 的 {protocol} relay 检测完整报告：模型 {model}，总分 {score:.0f}/100，结论 {verdict}。{total} 项检测中 {passed} 项通过，{failed} 项未通过。Clodex 从字段级检查 relay 的真实性和质量。",
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
        "seo_report_title": "{domain} {protocol} relay check: {score:.0f}/100 {verdict} | Clodex",
        "seo_report_description": "Full report for the {protocol} relay check on {domain}: model {model}, total score {score:.0f}/100, verdict {verdict}. {passed} of {total} checks passed and {failed} failed. Clodex inspects the relay at field level to reveal authenticity and quality.",
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
        "seo_report_title": "{domain}: проверка {protocol} relay, {score:.0f}/100 {verdict} | Clodex",
        "seo_report_description": "Полный отчёт проверки {protocol} relay для {domain}: модель {model}, итоговый счёт {score:.0f}/100, вердикт {verdict}. Пройдено {passed} из {total} проверок, ошибок: {failed}. Clodex проверяет relay на уровне полей, чтобы показать подлинность и качество.",
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

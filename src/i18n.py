"""
Every user-visible string in every email, in both supported languages.

One table, two columns. Adding a language means adding a key to _STRINGS and a
date formatter below — the reporters and agents never branch on language themselves,
they call t() / the formatters / prompt_language_directive().

Per the product decision, these stay in English in BOTH languages because they are
standard finance shorthand rather than prose: indicator names (RSI, MACD, EPS, QoQ,
YoY, P/E) and option jargon (CALL, PUT, ITM, ATM, OTM, LEAPS). Everything else —
section headers, sentiment badges, action labels, the product name — is translated.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.config import REPORT_LANGUAGE

_lang = REPORT_LANGUAGE


def set_language(lang: str) -> None:
    """Override the configured language. Intended for tests and previews."""
    global _lang
    if lang not in _STRINGS:
        raise ValueError(f"unsupported language {lang!r}")
    _lang = lang


def language() -> str:
    return _lang


_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # ── shared ────────────────────────────────────────────────────────────
        "brand":              "Stock Sentinel",
        "disclaimer":         "Not financial advice.",

        # ── daily report ──────────────────────────────────────────────────────
        "daily_stocks":       "{n} stocks",
        "daily_signals":      "{n} signal{s}",
        "daily_no_signals":   "No signals",

        "sec_scorecard":      "SCORECARD",
        "sec_earnings":       "UPCOMING EARNINGS",
        "sec_news":           "TOP NEWS",
        "sec_picks":          "SENTINEL PICKS",
        "sec_flow":           "OPTION FLOW",
        "sec_commentary":     "COMMENTARY",

        # ── degraded-run banner ───────────────────────────────────────────────
        "degraded_title":     "Some analysis unavailable",
        "degraded_line":      "{sections} could not be generated ({reason}).",
        "degraded_footer":    "Scorecard data is computed locally and is unaffected.",
        "list_sep":           ", ",
        "reason_credit":      "Anthropic API credit balance too low",
        "reason_auth":        "Anthropic API authentication failed",
        "reason_rate_limit":  "Anthropic API rate limit exceeded",
        "reason_network":     "network error",
        "reason_unknown":     "Anthropic API error",

        "col_ticker":         "Ticker",
        "col_rsi":            "RSI",
        "col_divergence":     "Divergence",
        "col_macd_zero":      "MACD&nbsp;Zero",
        "col_macd_cross":     "MACD&nbsp;Cross",
        "col_macd_hist":      "MACD&nbsp;Hist",
        "col_fwd_pe":         "Fwd&nbsp;PE",
        "col_daily":          "D",
        "col_weekly":         "W",

        "legend_text": (
            "RSI oversold/neutral/overbought &nbsp;·&nbsp; Divergence = price vs. RSI diverging "
            "&nbsp;·&nbsp; MACD (weekly) Zero = trend bias, Cross = timing trigger, Hist = momentum building/fading"
        ),
        "legend_bullish":     "bullish/oversold",
        "legend_neutral":     "neutral/mixed",
        "legend_bearish":     "bearish/overbought",
        "legend_none":        "no signal",

        "earn_today":         "Today",
        "earn_tomorrow":      "Tomorrow",
        "earn_in_days":       "in {n} days",
        "earn_bmo":           "Before Market",
        "earn_amc":           "After Market",

        "pick_accumulate":    "ACCUMULATE",
        "pick_trim":          "TRIM",

        "flow_caveat": (
            "Unusual volume vs. open interest, contracts expiring 4+ weeks out only. "
            "Open interest is prior-day settled and premium is estimated — directional reads are inferred, not confirmed."
        ),
        "sent_bullish":       "BULLISH",
        "sent_bearish":       "BEARISH",
        "sent_mixed":         "MIXED",
        "sent_neutral":       "NEUTRAL",

        # ── earnings report ───────────────────────────────────────────────────
        "er_title":           "Earnings Brief · {ticker}",
        "er_subtitle":        "Earnings Call Analysis",
        "er_sec_review":      "Pre-Earnings Review",
        "er_sec_metrics":     "Key Financials",
        "er_sec_highlights":  "Financial Highlights",
        "er_sec_talking":     "Management Takeaways",
        "er_sec_outlook":     "Outlook",
        "er_col_metric":      "Metric",
        "er_col_current":     "This Quarter",
        "er_col_qoq":         "QoQ",
        "er_col_yoy":         "YoY",
        "er_revenue":         "Revenue",
        "er_gross_margin":    "Gross Margin",
        "er_op_margin":       "Operating Margin",
        "er_net_income":      "Net Income",
        "er_eps":             "EPS",
        "er_no_financials":   "Financial data unavailable",
        "er_period":          "Period: {period}",
        "er_footer":          "Source: SEC EDGAR · yfinance · Not financial advice.",

        # ── pre-earnings report ───────────────────────────────────────────────
        "pe_title":           "Pre-Earnings Preview · {ticker}",
        "pe_subtitle":        "Pre-Earnings Preview",
        "pe_sec_watch":       "Watch Points",
        "pe_sec_history":     "Historical Earnings Moves",
        "pe_col_date":        "Earnings Date",
        "pe_col_pre":         "Prior 10 Sessions",
        "pe_col_post":        "Next 10 Sessions",
        "pe_post_note":       " ({have}/{n} with data)",
        "pe_avg":             "Average ({n} qtrs)",
        "pe_intro": (
            "Next earnings ({edate}) is {days_html} away. The table shows returns over "
            "the 10 trading days before and after each of the last {n} reports."
        ),
        "pe_days":            "{n} days",
        "pe_footer":          "Source: yfinance · Claude Haiku · Web search · Not financial advice.",
    },

    "zh": {
        # ── shared ────────────────────────────────────────────────────────────
        "brand":              "股市摘要",
        "disclaimer":         "非投资建议。",

        # ── daily report ──────────────────────────────────────────────────────
        "daily_stocks":       "{n} 只股票",
        "daily_signals":      "{n} 个信号",
        "daily_no_signals":   "无信号",

        "sec_scorecard":      "评分卡",
        "sec_earnings":       "即将公布财报",
        "sec_news":           "重点新闻",
        "sec_picks":          "精选操作",
        "sec_flow":           "期权异动",
        "sec_commentary":     "点评",

        # ── degraded-run banner ───────────────────────────────────────────────
        "degraded_title":     "部分分析不可用",
        "degraded_line":      "{sections} 未能生成（{reason}）。",
        "degraded_footer":    "评分卡数据为本地计算，不受影响。",
        "list_sep":           "、",
        "reason_credit":      "Anthropic API 信用额度不足",
        "reason_auth":        "Anthropic API 认证失败",
        "reason_rate_limit":  "Anthropic API 速率超限",
        "reason_network":     "网络错误",
        "reason_unknown":     "Anthropic API 错误",

        "col_ticker":         "股票",
        "col_rsi":            "RSI",
        "col_divergence":     "背离",
        "col_macd_zero":      "MACD&nbsp;零轴",
        "col_macd_cross":     "MACD&nbsp;交叉",
        "col_macd_hist":      "MACD&nbsp;柱",
        "col_fwd_pe":         "预期&nbsp;PE",
        "col_daily":          "日",
        "col_weekly":         "周",

        "legend_text": (
            "RSI 超卖/中性/超买 &nbsp;·&nbsp; 背离 = 股价与 RSI 走势背道而驰 "
            "&nbsp;·&nbsp; MACD（周线）零轴 = 趋势方向，交叉 = 时机信号，柱 = 动能增强/减弱"
        ),
        "legend_bullish":     "看涨/超卖",
        "legend_neutral":     "中性/混合",
        "legend_bearish":     "看跌/超买",
        "legend_none":        "无信号",

        "earn_today":         "今天",
        "earn_tomorrow":      "明天",
        "earn_in_days":       "{n} 天后",
        "earn_bmo":           "盘前",
        "earn_amc":           "盘后",

        "pick_accumulate":    "加仓",
        "pick_trim":          "减仓",

        "flow_caveat": (
            "成交量相对未平仓量异常，仅统计到期日在 4 周以上的合约。"
            "未平仓量为前一交易日结算值，权利金为估算值 —— 方向判断为推测，并非确认。"
        ),
        "sent_bullish":       "看涨",
        "sent_bearish":       "看跌",
        "sent_mixed":         "混合",
        "sent_neutral":       "中性",

        # ── earnings report ───────────────────────────────────────────────────
        "er_title":           "财报速递 · {ticker}",
        "er_subtitle":        "财报电话会议分析",
        "er_sec_review":      "财报前瞻回顾",
        "er_sec_metrics":     "关键财务指标",
        "er_sec_highlights":  "财务亮点",
        "er_sec_talking":     "管理层核心观点",
        "er_sec_outlook":     "前景解读",
        "er_col_metric":      "指标",
        "er_col_current":     "本季度",
        "er_col_qoq":         "QoQ",
        "er_col_yoy":         "YoY",
        "er_revenue":         "营收",
        "er_gross_margin":    "毛利率",
        "er_op_margin":       "运营利润率",
        "er_net_income":      "净利润",
        "er_eps":             "EPS",
        "er_no_financials":   "财务数据暂不可用",
        "er_period":          "报告期：{period}",
        "er_footer":          "数据来源：SEC EDGAR · yfinance · 非投资建议。",

        # ── pre-earnings report ───────────────────────────────────────────────
        "pe_title":           "财报前瞻 · {ticker}",
        "pe_subtitle":        "财报前瞻",
        "pe_sec_watch":       "本次财报关注要点",
        "pe_sec_history":     "历史财报行情",
        "pe_col_date":        "财报日期",
        "pe_col_pre":         "前10交易日",
        "pe_col_post":        "后10交易日",
        "pe_post_note":       "（{have}/{n}季有数据）",
        "pe_avg":             "均值（{n}季）",
        "pe_intro": (
            "距下次财报（{edate}）还有 {days_html}。"
            "下表显示过去 {n} 次财报前后各 10 个交易日的收益率。"
        ),
        "pe_days":            "{n} 天",
        "pe_footer":          "数据来源：yfinance · Claude Haiku · 网络搜索 · 非投资建议。",
    },
}


def t(key: str, **kwargs: Any) -> str:
    """Look up a localized string, formatting any {placeholders} with kwargs."""
    text = _STRINGS[_lang].get(key)
    if text is None:  # missing translation → fall back to English rather than crash the email
        text = _STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text


# ── date formatting ──────────────────────────────────────────────────────────

def fmt_date_long(d: date) -> str:
    """Header date, e.g. 'August 19, 2026' / '2026年8月19日'."""
    if _lang == "zh":
        return f"{d.year}年{d.month}月{d.day}日"
    return d.strftime("%B %d, %Y")


def fmt_date_short(d: date) -> str:
    """Subject-line date, e.g. 'Aug 19, 2026' / '2026年8月19日'."""
    if _lang == "zh":
        return f"{d.year}年{d.month}月{d.day}日"
    return d.strftime("%b %d, %Y")


def fmt_date_compact(d: date) -> str:
    """Table date, e.g. 'Aug 19' / '8月19日'."""
    if _lang == "zh":
        return f"{d.month}月{d.day}日"
    return d.strftime("%b %d")


# ── prompt localization ──────────────────────────────────────────────────────

_KEEP_ENGLISH = "RSI, MACD, EPS, QoQ, YoY, P/E, CALL, PUT, ITM, ATM, OTM, LEAPS"

_DIRECTIVE = {
    "zh": (
        "\n\nOUTPUT LANGUAGE: Write ALL of your output in Simplified Chinese (简体中文). "
        "Every field you return must be Chinese prose — no English sentences, clauses, or "
        "section labels. The ONLY things that stay in English are ticker symbols, company and "
        "product names, and these standard finance abbreviations: " + _KEEP_ENGLISH + "."
    ),
    "en": (
        "\n\nOUTPUT LANGUAGE: Write ALL of your output in English. "
        "Every field you return must be English prose — do not use Chinese characters anywhere."
    ),
}


def prompt_language_directive() -> str:
    """Appended to every agent system prompt so model output matches the email language."""
    return _DIRECTIVE[_lang]


def brief_length_hint() -> str:
    """Length guidance for short bullets, since character counts differ by language."""
    return "80 个汉字以内" if _lang == "zh" else "about 40 words or fewer"

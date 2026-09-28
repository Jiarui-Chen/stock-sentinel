import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import Dict, List, Any, Optional

from src.config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS, SMTP_HOST, SMTP_PORT,
    RSI_WATCH_THRESHOLD, RSI_WARN_THRESHOLD,
)
from src.i18n import t, fmt_date_long, fmt_date_short, fmt_date_compact
from src.degradation import SECTION_KEYS
from src.indicators import participation

_GREEN, _ORANGE, _RED = "#16a34a", "#d97706", "#dc2626"
_NONE_COLOR = "#d1d5db"  # neutral gray outline — no signal / insufficient data


def _circle(color: str) -> str:
    return f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};"></span>'


def _hollow_circle() -> str:
    return (
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:transparent;border:1.5px solid {_NONE_COLOR};"></span>'
    )


def _rsi_circle(val: Optional[float]) -> str:
    if val is None:
        return _hollow_circle()
    if val < RSI_WATCH_THRESHOLD:
        return _circle(_GREEN)
    if val < RSI_WARN_THRESHOLD:
        return _circle(_ORANGE)
    return _circle(_RED)


def _divergence_circle(div: Optional[str]) -> str:
    if div == "bullish":
        return _circle(_GREEN)
    if div == "bearish":
        return _circle(_RED)
    return _hollow_circle()


def _macd_zero_circle(sign: Optional[str]) -> str:
    if sign == "positive":
        return _circle(_GREEN)
    if sign == "negative":
        return _circle(_RED)
    return _hollow_circle()


def _macd_hist_circle(momentum: Optional[str]) -> str:
    if momentum == "increasing":
        return _circle(_GREEN)
    if momentum == "decreasing":
        return _circle(_RED)
    return _hollow_circle()


def _macd_cross_circle(cross: Optional[str]) -> str:
    if cross == "bullish":
        return _circle(_GREEN)
    if cross == "bearish":
        return _circle(_RED)
    return _hollow_circle()


def _pe_cell(val: Optional[float]) -> str:
    text = f"{val:.1f}" if val is not None else "—"
    return f'<td style="padding:6px 8px;font-size:11px;color:#374151;text-align:center;white-space:nowrap;">{text}</td>'


def _scorecard_header() -> str:
    def group(label: str) -> str:
        return (
            f'<td colspan="2" style="padding:5px 4px;font-size:8px;font-weight:bold;color:#9ca3af;'
            f'text-transform:uppercase;text-align:center;border-bottom:1px solid #e2e8f0;">{label}</td>'
        )

    def single(label: str) -> str:
        return (
            f'<td rowspan="2" style="padding:6px 4px;font-size:8px;font-weight:bold;color:#9ca3af;'
            f'text-transform:uppercase;text-align:center;vertical-align:bottom;border-bottom:1px solid #e2e8f0;">{label}</td>'
        )

    def sub(label: str) -> str:
        return f'<td style="padding:3px 4px 6px;font-size:8px;font-weight:bold;color:#9ca3af;text-align:center;">{label}</td>'

    row1 = (
        '<tr style="background:#f8fafc;">'
        '<td rowspan="2" style="padding:6px 8px 6px 12px;font-size:9px;font-weight:bold;color:#9ca3af;'
        'text-transform:uppercase;vertical-align:bottom;border-bottom:1px solid #e2e8f0;">' + t("col_ticker") + '</td>'
        + group(t("col_rsi")) + group(t("col_divergence"))
        + single(t("col_macd_zero")) + single(t("col_macd_cross")) + single(t("col_macd_hist"))
        + '<td rowspan="2" style="padding:6px 8px;font-size:9px;font-weight:bold;color:#9ca3af;text-transform:uppercase;'
          'text-align:center;vertical-align:bottom;border-bottom:1px solid #e2e8f0;">' + t("col_fwd_pe") + '</td>'
        + '</tr>'
    )
    row2 = (
        '<tr style="background:#f8fafc;">'
        + sub(t("col_daily")) + sub(t("col_weekly")) + sub(t("col_daily")) + sub(t("col_weekly"))
        + '</tr>'
    )
    return row1 + row2


def _scorecard_row(r: Dict) -> str:
    def cell(inner: str) -> str:
        return f'<td style="padding:7px 4px;text-align:center;">{inner}</td>'

    return f"""
        <tr style="border-top:1px solid #f1f5f9;">
            <td style="padding:7px 8px 7px 12px;font-weight:bold;font-size:12px;color:#111827;white-space:nowrap;">{r["ticker"]}</td>
            {cell(_rsi_circle(r.get("daily_rsi")))}
            {cell(_rsi_circle(r.get("weekly_rsi")))}
            {cell(_divergence_circle(r.get("daily_rsi_divergence")))}
            {cell(_divergence_circle(r.get("weekly_rsi_divergence")))}
            {cell(_macd_zero_circle(r.get("weekly_macd_line_sign")))}
            {cell(_macd_cross_circle(r.get("weekly_macd_cross")))}
            {cell(_macd_hist_circle(r.get("weekly_macd_hist_momentum")))}
            {_pe_cell(r.get("pe_forward"))}
        </tr>"""


def _scorecard_sort_key(r: Dict) -> tuple:
    def rsi_extreme(val: Optional[float]) -> int:
        if val is None:
            return 1
        return 0 if (val < RSI_WATCH_THRESHOLD or val >= RSI_WARN_THRESHOLD) else 1

    has_extreme_rsi = min(rsi_extreme(r.get("daily_rsi")), rsi_extreme(r.get("weekly_rsi")))
    has_divergence  = 0 if (r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")) else 1
    has_cross       = 0 if r.get("weekly_macd_cross") else 1
    return (has_extreme_rsi, has_divergence, has_cross)


def _scorecard_legend() -> str:
    text = t("legend_text")
    key = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;padding:4px 0 0;font-size:10px;color:#374151;">'
        f'<span>{_circle(_GREEN)}&nbsp;{t("legend_bullish")}</span>'
        f'<span>{_circle(_ORANGE)}&nbsp;{t("legend_neutral")}</span>'
        f'<span>{_circle(_RED)}&nbsp;{t("legend_bearish")}</span>'
        f'<span>{_hollow_circle()}&nbsp;{t("legend_none")}</span>'
        '</div>'
    )

    return f"""
        <div style="padding:8px 16px;font-size:10.5px;line-height:1.5;color:#6b7280;border-bottom:1px solid #f1f5f9;">
            {text}
            {key}
        </div>"""


def _scorecard_block(results: List[Dict]) -> str:
    if not results:
        return ""
    rows = "".join(_scorecard_row(r) for r in sorted(results, key=_scorecard_sort_key))
    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
        <div style="padding:10px 16px;background:#1e3a5f;">
            <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">{t("sec_scorecard")}</span>
        </div>
        {_scorecard_legend()}
        <div style="overflow-x:auto;">
            <table style="border-collapse:collapse;width:100%;">
                {_scorecard_header()}
                {rows}
            </table>
        </div>
    </div>"""


def _upcoming_earnings_block(results: List[Dict]) -> str:
    today   = date.today()
    entries = []
    for r in results:
        ed_str = r.get("earnings_date")
        if not ed_str:
            continue
        try:
            ed = date.fromisoformat(ed_str)
            days_until = (ed - today).days
            if 0 <= days_until <= 14:
                entries.append((r["ticker"], ed, days_until, r.get("earnings_timing")))
        except Exception:
            continue

    if not entries:
        return ""

    entries.sort(key=lambda x: x[1])
    rows_html = ""
    for ticker, ed, days_until, timing in entries:
        label     = fmt_date_compact(ed)
        countdown = (
            t("earn_today")    if days_until == 0 else
            t("earn_tomorrow") if days_until == 1 else
            t("earn_in_days", n=days_until)
        )
        color     = "#dc2626" if days_until <= 1 else "#d97706"
        timing_html = {
            "BMO": f' &nbsp;<span style="color:#6b7280;font-size:11px;">{t("earn_bmo")}</span>',
            "AMC": f' &nbsp;<span style="color:#6b7280;font-size:11px;">{t("earn_amc")}</span>',
        }.get(timing, "")
        rows_html += (
            f'<tr>'
            f'<td style="padding:7px 8px 7px 16px;font-weight:bold;font-size:13px;color:#111827;white-space:nowrap;">{ticker}</td>'
            f'<td style="padding:7px 8px;font-size:12px;">'
            f'<span style="font-weight:bold;color:{color};">{label}</span>{timing_html}</td>'
            f'<td style="padding:7px 16px 7px 8px;font-size:11px;color:#9ca3af;text-align:right;">{countdown}</td>'
            f'</tr>'
        )

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
        <div style="padding:10px 16px;background:#1e3a5f;border-bottom:1px solid #e2e8f0;">
            <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">{t("sec_earnings")}</span>
        </div>
        <table style="width:100%;border-collapse:collapse;">
            {rows_html}
        </table>
    </div>"""


def _top_news_block(top_news: List[Dict]) -> str:
    if not top_news:
        return ""

    items = ""
    for n in top_news:
        sentiment   = (n.get("news_sentiment") or "").lower()
        sent_color  = {"bullish": "#16a34a", "bearish": "#dc2626"}.get(sentiment, "#6b7280")
        sent_text   = t(f"sent_{sentiment}") if sentiment in ("bullish", "bearish", "mixed", "neutral") else ""
        sent_label  = f'<span style="color:{sent_color};font-weight:bold;">{sent_text}</span>  ' if sent_text else ""
        implication = n.get("news_implication") or ""
        impl_html   = f'<div style="color:#6b7280;margin-top:3px;">{implication}</div>' if implication else ""
        items += f"""
        <div style="padding:10px 0;border-top:1px solid #f1f5f9;">
            <div style="font-weight:bold;font-size:13px;color:#111827;margin-bottom:3px;">{n["ticker"]}</div>
            <div style="font-size:12px;color:#374151;line-height:1.6;">{sent_label}{n.get("news_summary", "")}</div>
            {impl_html}
        </div>"""

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
        <div style="padding:10px 16px;background:#1e3a5f;">
            <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">{t("sec_news")}</span>
        </div>
        <div style="padding:0 16px;">{items}</div>
    </div>"""


def _analyst_picks_block(picks: Dict) -> str:
    buy  = picks.get("buy",  [])
    sell = picks.get("sell", [])
    if not buy and not sell:
        return ""

    def pick_rows(items: list, color: str, arrow: str, label: str) -> str:
        rows = ""
        for p in items:
            rows += f"""
            <tr>
                <td style="padding:8px 12px 8px 0;vertical-align:top;white-space:nowrap;">
                    <span style="font-weight:bold;font-size:13px;color:{color};">{arrow} {p["ticker"]}</span>
                    <div style="font-size:10px;color:{color};opacity:0.85;letter-spacing:0.5px;">{label}</div>
                </td>
                <td style="padding:8px 0;font-size:12px;color:#374151;line-height:1.5;">
                    {p["reason"]}
                </td>
            </tr>"""
        return rows

    buy_rows  = pick_rows(buy,  "#16a34a", "▲", t("pick_accumulate"))
    sell_rows = pick_rows(sell, "#dc2626", "▼", t("pick_trim"))

    divider = '<tr><td colspan="2"><div style="border-top:1px solid #e2e8f0;margin:6px 0;"></div></td></tr>' if buy and sell else ""

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
        <div style="padding:10px 16px;background:#0f172a;border-bottom:1px solid #e2e8f0;">
            <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">{t("sec_picks")}</span>
        </div>
        <div style="padding:10px 16px;">
            <table style="width:100%;border-collapse:collapse;">
                {buy_rows}
                {divider}
                {sell_rows}
            </table>
        </div>
    </div>"""


def _signal_count(results: List[Dict]) -> int:
    return len([
        r for r in results
        if r.get("daily_alert") or r.get("weekly_alert")
        or r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")
    ])


def _option_flow_block(flows: List[Dict]) -> str:
    """Top flows across the whole watchlist, one bullet per ticker (see option_flow_analyzer)."""
    if not flows:
        return ""

    items = ""
    for f in flows:
        sentiment  = (f.get("sentiment") or "").lower()
        color      = {"bullish": "#16a34a", "bearish": "#dc2626"}.get(sentiment, "#d97706")
        sent_text  = t(f"sent_{sentiment}") if sentiment in ("bullish", "bearish", "mixed", "neutral") else ""
        sent_label = (
            f'<span style="color:{color};font-weight:bold;font-size:11px;">{sent_text}</span>'
            if sent_text else ""
        )
        contracts  = f.get("contracts") or ""
        contracts_html = (
            f'<span style="font-family:monospace;font-size:11px;color:#6b7280;">{contracts}</span>'
            if contracts else ""
        )
        sep = ' &nbsp;·&nbsp; ' if sent_label and contracts_html else ""
        items += f"""
        <div style="padding:10px 0;border-top:1px solid #f1f5f9;">
            <div style="margin-bottom:3px;">
                <span style="font-weight:bold;font-size:13px;color:#111827;">{f["ticker"]}</span>
                &nbsp;&nbsp;{sent_label}{sep}{contracts_html}
            </div>
            <div style="font-size:12px;color:#374151;line-height:1.6;">{f["summary"]}</div>
        </div>"""

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
        <div style="padding:10px 16px;background:#1e3a5f;">
            <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">{t("sec_flow")}</span>
        </div>
        <div style="padding:8px 16px 0;font-size:10.5px;line-height:1.5;color:#6b7280;">
            {t("flow_caveat")}
        </div>
        <div style="padding:0 16px;">{items}</div>
    </div>"""


_ZONE_COLORS = {"strong": _GREEN, "mixed": _ORANGE, "weak": _RED}

_PART_ROWS = (
    ("part_short", 20),
    ("part_mid",   50),
    ("part_long", 100),
)


def _participation_block(part: Optional[Dict[str, Any]]) -> str:
    """
    Market breadth: share of S&P 500 constituents above their 20/50/100-day SMA.

    Leads the report because it frames everything below it — the same RSI reading
    means different things in a market where 70% of names are above their 20-day
    average and one where 30% are.

    Each row carries a text zone label as well as a colored dot: color alone is
    not a signal a colorblind reader or a plain-text client can resolve.
    """
    if not part:
        return ""

    windows = part.get("windows") or {}
    rows = ""
    for label_key, window in _PART_ROWS:
        pct = windows.get(window)
        if pct is None:
            continue
        z = participation.zone(pct)
        color = _ZONE_COLORS[z]
        rows += f"""
        <tr>
            <td style="padding:7px 0;font-size:12px;color:#374151;white-space:nowrap;">
                <span style="font-weight:bold;">{t(label_key)}</span>
                <span style="color:#9ca3af;">&nbsp;·&nbsp;{t("part_ma", n=window)}</span>
            </td>
            <td style="padding:7px 0;text-align:right;font-size:16px;font-weight:bold;
                       color:{color};white-space:nowrap;">{pct:.1f}%</td>
            <td style="padding:7px 0 7px 10px;text-align:right;font-size:10px;
                       color:{color};letter-spacing:0.5px;white-space:nowrap;">
                {_circle(color)}&nbsp;{t(f"zone_{z}")}
            </td>
        </tr>"""

    if not rows:
        return ""

    stale = (f'&nbsp;·&nbsp;{t("part_stale")}' if part.get("universe_stale") else "")
    footnote = t("part_footnote", n=part.get("universe", 0), asof=part.get("as_of", "")) + stale

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
        <div style="padding:10px 16px;background:#1e3a5f;">
            <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">{t("sec_participation")}</span>
        </div>
        <div style="padding:10px 16px 12px;">
            <div style="font-size:11px;color:#6b7280;padding-bottom:4px;">{t("part_caption")}</div>
            <table style="width:100%;border-collapse:collapse;">{rows}</table>
            <div style="font-size:10px;color:#9ca3af;padding-top:8px;border-top:1px solid #f1f5f9;">
                {footnote}
            </div>
        </div>
    </div>"""


def _degraded_block(degradations: List[tuple]) -> str:
    """
    Warning strip naming the sections that failed to generate, and why.

    An empty section is ambiguous on its own — a quiet news day and a dead API
    look the same — so without this a total analysis outage produces a
    normal-looking email. Rendered at the top, above the surviving content.
    """
    if not degradations:
        return ""

    # Group sections by cause, so one outage reads as one line rather than four.
    by_reason: Dict[str, List[str]] = {}
    for section, reason in degradations:
        label = t(SECTION_KEYS[section])
        by_reason.setdefault(reason, [])
        if label not in by_reason[reason]:
            by_reason[reason].append(label)

    lines = "".join(
        f'<div style="margin:3px 0 0;">'
        f'{t("degraded_line", sections=t("list_sep").join(labels), reason=t(reason))}'
        f"</div>"
        for reason, labels in by_reason.items()
    )

    return f"""
    <div style="background:#fffbeb;border:1px solid #fcd34d;border-left:4px solid #f59e0b;
                border-radius:6px;padding:12px 14px;margin:16px 0 4px;">
        <div style="font-size:13px;font-weight:bold;color:#92400e;">
            &#9888;&#65039;&nbsp;{t("degraded_title")}
        </div>
        <div style="font-size:12px;color:#92400e;line-height:1.55;">
            {lines}
            <div style="margin:5px 0 0;color:#a16207;">{t("degraded_footer")}</div>
        </div>
    </div>"""


def build_html(
    results: List[Dict[str, Any]],
    analyst_picks: Optional[Dict] = None,
    top_news: Optional[List[Dict]] = None,
    option_flows: Optional[List[Dict]] = None,
    degradations: Optional[List[tuple]] = None,
    part: Optional[Dict[str, Any]] = None,
) -> str:
    today = fmt_date_long(date.today())

    signal_count = _signal_count(results)
    alert_label = (
        t("daily_signals", n=signal_count, s="s" if signal_count != 1 else "")
        if signal_count else t("daily_no_signals")
    )
    stocks_label = t("daily_stocks", n=len(results))

    degraded_block = _degraded_block(degradations or [])
    part_block     = _participation_block(part)
    picks_block    = _analyst_picks_block(analyst_picks) if analyst_picks else ""
    earnings_block = _upcoming_earnings_block(results)
    news_block     = _top_news_block(top_news or [])
    scorecard      = _scorecard_block(results)
    flow_block     = _option_flow_block(option_flows or [])

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;color:#111827;background:#ffffff;">

    <div style="background:#0f172a;color:white;padding:22px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;letter-spacing:0.3px;">{t("brand")}</h1>
        <p style="margin:5px 0 0;color:#94a3b8;font-size:13px;">
            {today}&nbsp;&nbsp;·&nbsp;&nbsp;{stocks_label}&nbsp;&nbsp;·&nbsp;&nbsp;{alert_label}
        </p>
    </div>

    <div style="padding:4px 24px 24px;">
        {degraded_block}
        {part_block}
        {picks_block}
        {earnings_block}
        {news_block}
        {scorecard}
        {flow_block}
    </div>

    <div style="background:#f1f5f9;padding:12px 24px;text-align:center;color:#9ca3af;font-size:11px;border-radius:0 0 8px 8px;">
        {t("disclaimer")}
    </div>

</body>
</html>"""


def send(
    results: List[Dict[str, Any]],
    analyst_picks: Optional[Dict] = None,
    top_news: Optional[List[Dict]] = None,
    option_flows: Optional[List[Dict]] = None,
    degradations: Optional[List[tuple]] = None,
    part: Optional[Dict[str, Any]] = None,
) -> None:
    today = fmt_date_short(date.today())
    signal_count = _signal_count(results)
    subject = f'{t("brand")} — {today}'
    if signal_count:
        label = t("daily_signals", n=signal_count, s="s" if signal_count != 1 else "")
        subject += f" ({label})"

    html = build_html(results, analyst_picks, top_news, option_flows, degradations, part)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(EMAIL_RECIPIENTS)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_SENDER, EMAIL_RECIPIENTS, msg.as_string())

    print(f"[OK] Report sent — {subject}")

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from typing import List, Dict, Any, Optional
from src.config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_HOST, SMTP_PORT


def _fmt(val: Optional[float]) -> str:
    return f"{val:.1f}" if val is not None else "—"


def _rsi_color(alert: Optional[str]) -> str:
    if alert in {"strong_buy", "consider_buy"}:
        return "#16a34a"
    if alert in {"watch", "warn"}:
        return "#d97706"
    if alert in {"consider_sell", "strong_sell"}:
        return "#dc2626"
    return "#374151"


def _rsi_span(val: str, alert: Optional[str]) -> str:
    label = f' <span style="font-weight:bold;">{alert.replace("_", " ").upper()}</span>' if alert else ""
    return f'<span style="color:{_rsi_color(alert)};">{val}{label}</span>'


def _macd_hist_span(sign: Optional[str], momentum: Optional[str]) -> str:
    if not sign or not momentum:
        return '<span style="color:#9ca3af;">—</span>'
    sym = ("+" if sign == "positive" else "−") + ("↑" if momentum == "increasing" else "↓")
    if sign == "positive" and momentum == "increasing":
        color = "#16a34a"
    elif sign == "negative" and momentum == "decreasing":
        color = "#dc2626"
    else:
        color = "#d97706"
    return f'<span style="font-weight:bold;color:{color};">{sym}</span>'


def _label_cell(text: str) -> str:
    return f'<td style="padding:9px 12px 9px 16px;color:#9ca3af;font-size:10px;font-weight:bold;text-transform:uppercase;white-space:nowrap;vertical-align:top;width:80px;">{text}</td>'


def _ticker_card(r: Dict) -> str:
    rows = ""

    # News
    if r.get("news_summary"):
        sentiment = r.get("news_sentiment") or ""
        sent_color = {"bullish": "#16a34a", "bearish": "#dc2626"}.get(sentiment, "#6b7280")
        sent_label = f'<span style="color:{sent_color};font-weight:bold;">{sentiment.upper()}</span>  ' if sentiment else ""
        implication = r.get("news_implication") or ""
        impl = f'<div style="color:#6b7280;margin-top:3px;">{implication}</div>' if implication else ""
        rows += f"""
            <tr>
                {_label_cell("News")}
                <td style="padding:9px 16px;font-size:12px;color:#374151;">{sent_label}{r["news_summary"]}{impl}</td>
            </tr>"""

    # RSI
    rows += f"""
        <tr style="border-top:1px solid #f1f5f9;">
            {_label_cell("RSI")}
            <td style="padding:9px 16px;font-size:12px;">
                Daily {_rsi_span(_fmt(r.get("daily_rsi")), r.get("daily_alert"))}
                <span style="color:#d1d5db;"> &nbsp;|&nbsp; </span>
                Weekly {_rsi_span(_fmt(r.get("weekly_rsi")), r.get("weekly_alert"))}
            </td>
        </tr>"""

    # RSI Divergence
    d_div = r.get("daily_rsi_divergence")
    w_div = r.get("weekly_rsi_divergence")
    if d_div or w_div:
        def _div_span(div: str, tf: str) -> str:
            color = "#16a34a" if div == "bullish" else "#dc2626"
            return f'{tf} <span style="color:{color};font-weight:bold;">{div.upper()} DIV</span>'
        parts = list(filter(None, [
            _div_span(d_div, "Daily") if d_div else "",
            _div_span(w_div, "Weekly") if w_div else "",
        ]))
        rows += f"""
        <tr style="border-top:1px solid #f1f5f9;">
            {_label_cell("Divergence")}
            <td style="padding:9px 16px;font-size:12px;">{"<span style='color:#d1d5db;'> &nbsp;|&nbsp; </span>".join(parts)}</td>
        </tr>"""

    # MACD Histogram
    rows += f"""
        <tr style="border-top:1px solid #f1f5f9;">
            {_label_cell("MACD Hist")}
            <td style="padding:9px 16px;font-size:12px;color:#374151;">
                Daily {_macd_hist_span(r.get("daily_macd_hist_sign"), r.get("daily_macd_hist_momentum"))}
                <span style="color:#d1d5db;"> &nbsp;|&nbsp; </span>
                Weekly {_macd_hist_span(r.get("weekly_macd_hist_sign"), r.get("weekly_macd_hist_momentum"))}
            </td>
        </tr>"""

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:6px;margin:10px 0;overflow:hidden;">
        <div style="padding:9px 16px;background:#f8fafc;border-bottom:1px solid #e2e8f0;">
            <span style="font-weight:bold;font-size:14px;color:#111827;">{r["ticker"]}</span>
        </div>
        <table style="width:100%;border-collapse:collapse;">
            {rows}
        </table>
    </div>"""


def _sort_key(r: Dict) -> tuple:
    priority = {
        "strong_buy": 0, "strong_sell": 0,
        "consider_buy": 1, "consider_sell": 1,
        "watch": 2, "warn": 2,
    }
    alert_rank = min(
        priority.get(r.get("daily_alert"), 3),
        priority.get(r.get("weekly_alert"), 3),
    )
    has_div = 0 if (r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")) else 1
    has_news = 0 if r.get("news_summary") else 1
    return (alert_rank, has_div, has_news)


def build_html(results: List[Dict[str, Any]], summary: str) -> str:
    today = date.today().strftime("%B %d, %Y")

    signal_count = len([
        r for r in results
        if r.get("daily_alert") or r.get("weekly_alert")
        or r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")
    ])
    alert_label = f"{signal_count} signal{'s' if signal_count != 1 else ''}" if signal_count else "No signals"

    summary_block = f"""
    <div style="margin:20px 0;padding:14px 16px;background:#f8fafc;border-left:3px solid #94a3b8;border-radius:4px;">
        <p style="margin:0;color:#374151;font-size:13px;">{summary}</p>
    </div>""" if summary else ""

    ticker_cards = "".join(_ticker_card(r) for r in sorted(results, key=_sort_key))

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;color:#111827;background:#ffffff;">

    <div style="background:#0f172a;color:white;padding:22px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;letter-spacing:0.3px;">Stock Sentinel</h1>
        <p style="margin:5px 0 0;color:#94a3b8;font-size:13px;">
            {today}&nbsp;&nbsp;·&nbsp;&nbsp;{len(results)} stocks&nbsp;&nbsp;·&nbsp;&nbsp;{alert_label}
        </p>
    </div>

    <div style="padding:4px 24px 24px;">
        {summary_block}
        {ticker_cards}
    </div>

    <div style="background:#f1f5f9;padding:12px 24px;text-align:center;color:#9ca3af;font-size:11px;border-radius:0 0 8px 8px;">
        RSI: &lt;35 watch · &lt;30 consider buy · &lt;25 strong buy · &gt;65 warn · &gt;70 consider sell · &gt;75 strong sell · Not financial advice.
    </div>

</body>
</html>"""


def send(results: List[Dict[str, Any]], summary: str) -> None:
    today = date.today().strftime("%b %d, %Y")
    signal_count = len([
        r for r in results
        if r.get("daily_alert") or r.get("weekly_alert")
        or r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")
    ])
    subject = f"Stock Sentinel — {today}"
    if signal_count:
        subject += f" ({signal_count} signal{'s' if signal_count != 1 else ''})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(build_html(results, summary), "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

    print(f"[OK] Report sent — {subject}")

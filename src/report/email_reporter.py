import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from typing import List, Dict, Any, Optional
from src.config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_HOST, SMTP_PORT

_BUY_ALERTS  = {"strong_buy", "consider_buy", "watch"}
_SELL_ALERTS = {"strong_sell", "consider_sell", "warn"}


# ── Signal helpers ────────────────────────────────────────────────────────────

def _is_buy(r: Dict, tf: str) -> bool:
    return r[f"{tf}_alert"] in _BUY_ALERTS or r.get(f"{tf}_rsi_divergence") == "bullish"


def _is_sell(r: Dict, tf: str) -> bool:
    return r[f"{tf}_alert"] in _SELL_ALERTS or r.get(f"{tf}_rsi_divergence") == "bearish"


# ── Badges & styles ───────────────────────────────────────────────────────────

def _badge(alert: Optional[str]) -> str:
    styles = {
        "strong_buy":    ("#14532d", "STRONG BUY"),
        "consider_buy":  ("#16a34a", "CONSIDER BUY"),
        "watch":         ("#15803d", "WATCH"),
        "warn":          ("#d97706", "WARN"),
        "consider_sell": ("#dc2626", "CONSIDER SELL"),
        "strong_sell":   ("#7f1d1d", "STRONG SELL"),
    }
    if alert in styles:
        bg, label = styles[alert]
        return f'<span style="background:{bg};color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:bold;">{label}</span>'
    return ""


def _rsi_div_badge(divergence: Optional[str]) -> str:
    if divergence == "bullish":
        return '<span style="background:#16a34a;color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:bold;">BULL RSI DIV</span>'
    if divergence == "bearish":
        return '<span style="background:#dc2626;color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:bold;">BEAR RSI DIV</span>'
    return ""


def _rsi_style(alert: Optional[str]) -> str:
    if alert == "strong_buy":
        return "color:#14532d;font-weight:bold;"
    if alert == "strong_sell":
        return "color:#7f1d1d;font-weight:bold;"
    if alert == "consider_buy":
        return "color:#16a34a;font-weight:bold;"
    if alert == "consider_sell":
        return "color:#dc2626;font-weight:bold;"
    if alert == "watch":
        return "color:#15803d;font-weight:bold;"
    if alert == "warn":
        return "color:#d97706;font-weight:bold;"
    return "color:#374151;"


def _fmt(val: Optional[float]) -> str:
    return f"{val:.1f}" if val is not None else "N/A"


def _signals(r: Dict, alert_key: str, div_key: str) -> str:
    return " ".join(filter(None, [_badge(r.get(alert_key)), _rsi_div_badge(r.get(div_key))]))


# ── Section builders ──────────────────────────────────────────────────────────

def _section(title: str, items: List[Dict], rsi_key: str, alert_key: str, div_key: str, sort_asc: bool = True) -> str:
    if not items:
        return ""

    rows = ""
    for r in sorted(items, key=lambda x: (x[rsi_key] or 999), reverse=not sort_asc):
        commentary = r.get("commentary")
        commentary_row = f"""
            <tr>
                <td colspan="3" style="padding:0 12px 10px 12px;color:#6b7280;font-size:12px;font-style:italic;">{commentary}</td>
            </tr>""" if commentary else ""
        rows += f"""
            <tr style="border-top:1px solid #e2e8f0;">
                <td style="padding:10px 12px;font-weight:bold;">{r["ticker"]}</td>
                <td style="padding:10px 12px;{_rsi_style(r.get(alert_key))}">{_fmt(r.get(rsi_key))}</td>
                <td style="padding:10px 12px;">{_signals(r, alert_key, div_key)}</td>
            </tr>{commentary_row}"""

    return f"""
        <div style="margin:20px 0;">
            <h2 style="font-size:14px;font-weight:bold;margin-bottom:8px;color:#111827;">{title}</h2>
            <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:6px;overflow:hidden;">
                <thead><tr style="background:#e2e8f0;font-size:11px;text-transform:uppercase;color:#6b7280;">
                    <th style="padding:7px 12px;text-align:left;">Ticker</th>
                    <th style="padding:7px 12px;text-align:left;">RSI</th>
                    <th style="padding:7px 12px;text-align:left;">Signal</th>
                </tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>"""


def _conflict_section(items: List[Dict]) -> str:
    if not items:
        return ""

    rows = ""
    for r in sorted(items, key=lambda x: x["ticker"]):
        commentary = r.get("commentary")
        commentary_row = f"""
            <tr>
                <td colspan="5" style="padding:0 12px 10px 12px;color:#6b7280;font-size:12px;font-style:italic;">{commentary}</td>
            </tr>""" if commentary else ""
        rows += f"""
            <tr style="border-top:1px solid #e2e8f0;">
                <td style="padding:10px 12px;font-weight:bold;">{r["ticker"]}</td>
                <td style="padding:10px 12px;{_rsi_style(r.get('daily_alert'))}">{_fmt(r.get('daily_rsi'))}</td>
                <td style="padding:10px 12px;">{_signals(r, 'daily_alert', 'daily_rsi_divergence')}</td>
                <td style="padding:10px 12px;{_rsi_style(r.get('weekly_alert'))}">{_fmt(r.get('weekly_rsi'))}</td>
                <td style="padding:10px 12px;">{_signals(r, 'weekly_alert', 'weekly_rsi_divergence')}</td>
            </tr>{commentary_row}"""

    return f"""
        <div style="margin:20px 0;">
            <h2 style="font-size:14px;font-weight:bold;margin-bottom:8px;color:#111827;">⚠️ Conflicting Signals</h2>
            <table style="width:100%;border-collapse:collapse;background:#fffbeb;border-radius:6px;overflow:hidden;border:1px solid #fde68a;">
                <thead><tr style="background:#fef3c7;font-size:11px;text-transform:uppercase;color:#92400e;">
                    <th style="padding:7px 12px;text-align:left;">Ticker</th>
                    <th style="padding:7px 12px;text-align:left;">Daily RSI</th>
                    <th style="padding:7px 12px;text-align:left;">Daily Signal</th>
                    <th style="padding:7px 12px;text-align:left;">Weekly RSI</th>
                    <th style="padding:7px 12px;text-align:left;">Weekly Signal</th>
                </tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>"""


def _watchlist_table(results: List[Dict]) -> str:
    rows = "".join(f"""
        <tr style="border-top:1px solid #e2e8f0;">
            <td style="padding:9px 12px;font-weight:bold;">{r["ticker"]}</td>
            <td style="padding:9px 12px;{_rsi_style(r.get('daily_alert'))}">{_fmt(r.get('daily_rsi'))}</td>
            <td style="padding:9px 12px;">{_signals(r, 'daily_alert', 'daily_rsi_divergence')}</td>
            <td style="padding:9px 12px;{_rsi_style(r.get('weekly_alert'))}">{_fmt(r.get('weekly_rsi'))}</td>
            <td style="padding:9px 12px;">{_signals(r, 'weekly_alert', 'weekly_rsi_divergence')}</td>
        </tr>"""
        for r in results
    )
    return f"""
        <div style="margin:20px 0;">
            <h2 style="font-size:14px;font-weight:bold;margin-bottom:8px;color:#111827;">Full Watchlist</h2>
            <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:6px;overflow:hidden;">
                <thead><tr style="background:#e2e8f0;font-size:11px;text-transform:uppercase;color:#6b7280;">
                    <th style="padding:7px 12px;text-align:left;">Ticker</th>
                    <th style="padding:7px 12px;text-align:left;">Daily RSI</th>
                    <th style="padding:7px 12px;text-align:left;">Short-term</th>
                    <th style="padding:7px 12px;text-align:left;">Weekly RSI</th>
                    <th style="padding:7px 12px;text-align:left;">Long-term</th>
                </tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>"""


def _st_compact(items: List[Dict]) -> str:
    """Single compact table for all short-term signals — no buy/sell split."""
    if not items:
        return ""
    rows = ""
    for r in sorted(items, key=lambda x: (x["daily_rsi"] or 999)):
        rows += f"""
            <tr style="border-top:1px solid #e2e8f0;">
                <td style="padding:8px 12px;font-weight:bold;">{r["ticker"]}</td>
                <td style="padding:8px 12px;{_rsi_style(r.get('daily_alert'))}">{_fmt(r.get('daily_rsi'))}</td>
                <td style="padding:8px 12px;">{_signals(r, 'daily_alert', 'daily_rsi_divergence')}</td>
            </tr>"""
    return f"""
        <div style="margin:20px 0;">
            <p style="font-size:12px;font-weight:bold;text-transform:uppercase;color:#6b7280;letter-spacing:0.5px;margin:0 0 8px;">Short-term (Daily RSI)</p>
            <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:6px;overflow:hidden;">
                <thead><tr style="background:#e2e8f0;font-size:11px;text-transform:uppercase;color:#6b7280;">
                    <th style="padding:7px 12px;text-align:left;">Ticker</th>
                    <th style="padding:7px 12px;text-align:left;">Daily RSI</th>
                    <th style="padding:7px 12px;text-align:left;">Signal</th>
                </tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>"""


def _divider() -> str:
    return '<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">'


# ── Main builders ─────────────────────────────────────────────────────────────

def build_html(results: List[Dict[str, Any]], summary: str) -> str:
    today = date.today().strftime("%B %d, %Y")

    # Classify each ticker per timeframe
    st_conflict_tickers = {r["ticker"] for r in results if _is_buy(r, "daily")  and _is_sell(r, "daily")}
    lt_conflict_tickers = {r["ticker"] for r in results if _is_buy(r, "weekly") and _is_sell(r, "weekly")}
    conflict_tickers    = st_conflict_tickers | lt_conflict_tickers

    st_buy   = [r for r in results if _is_buy(r, "daily")  and r["ticker"] not in st_conflict_tickers]
    st_sell  = [r for r in results if _is_sell(r, "daily") and r["ticker"] not in st_conflict_tickers]
    lt_buy   = [r for r in results if _is_buy(r, "weekly")  and r["ticker"] not in lt_conflict_tickers]
    lt_sell  = [r for r in results if _is_sell(r, "weekly") and r["ticker"] not in lt_conflict_tickers]
    conflict = [r for r in results if r["ticker"] in conflict_tickers]

    total_signals = len({r["ticker"] for r in st_buy + st_sell + lt_buy + lt_sell + conflict})
    alert_label = f"{total_signals} signal{'s' if total_signals != 1 else ''}" if total_signals else "No signals"

    summary_block = f"""
        <div style="margin:20px 0;padding:14px 16px;background:#eff6ff;border-left:4px solid #3b82f6;border-radius:4px;">
            <p style="margin:0;color:#1e40af;font-size:13px;">{summary}</p>
        </div>""" if summary else ""

    has_lt = lt_buy or lt_sell
    st_all = sorted(
        {r["ticker"]: r for r in st_buy + st_sell}.values(),
        key=lambda x: x["daily_rsi"] or 999
    )

    long_term_block = f"""
        <p style="font-size:12px;font-weight:bold;text-transform:uppercase;color:#6b7280;letter-spacing:0.5px;margin:24px 0 0;">Long-term (Weekly RSI)</p>
        {_section("🟢 Buy Signals",  lt_buy,  "weekly_rsi", "weekly_alert", "weekly_rsi_divergence", sort_asc=True)}
        {_section("🔴 Sell Signals", lt_sell, "weekly_rsi", "weekly_alert", "weekly_rsi_divergence", sort_asc=False)}""" if has_lt else ""

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
        {long_term_block}
        {_divider() if conflict else ""}
        {_conflict_section(conflict)}
        {_divider()}
        {_st_compact(st_all)}
        {_divider()}
        {_watchlist_table(results)}
    </div>

    <div style="background:#f1f5f9;padding:12px 24px;text-align:center;color:#9ca3af;font-size:11px;border-radius:0 0 8px 8px;">
        Buy: &lt;35 watch · &lt;30 consider buy · &lt;25 strong buy&nbsp;&nbsp;·&nbsp;&nbsp;Sell: &gt;65 warn · &gt;70 consider sell · &gt;75 strong sell&nbsp;&nbsp;·&nbsp;&nbsp;Not financial advice.
    </div>

</body>
</html>"""


def send(results: List[Dict[str, Any]], summary: str) -> None:
    today = date.today().strftime("%b %d, %Y")
    signal_count = len({
        r["ticker"] for r in results
        if r["daily_alert"] or r["weekly_alert"]
        or r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")
    })
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

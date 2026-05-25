import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from typing import List, Dict, Any, Optional
from src.config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_HOST, SMTP_PORT


def _badge(alert: Optional[str]) -> str:
    if alert == "consider_buy":
        return '<span style="background:#dc2626;color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:bold;">CONSIDER BUY</span>'
    if alert == "watch":
        return '<span style="background:#d97706;color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:bold;">WATCH</span>'
    return ""


def _rsi_style(alert: Optional[str]) -> str:
    if alert == "consider_buy":
        return "color:#dc2626;font-weight:bold;"
    if alert == "watch":
        return "color:#d97706;font-weight:bold;"
    return "color:#374151;"


def _fmt(val: Optional[float]) -> str:
    return f"{val:.1f}" if val is not None else "N/A"


def _alert_section(title: str, items: List[Dict], rsi_key: str, alert_key: str) -> str:
    if not items:
        return f"""
        <div style="margin:24px 0;">
            <h2 style="color:#1e40af;font-size:15px;margin-bottom:10px;">{title}</h2>
            <p style="color:#6b7280;font-size:13px;margin:0;">No alerts.</p>
        </div>"""

    rows = ""
    for r in sorted(items, key=lambda x: (x[rsi_key] or 999)):
        commentary = r.get("commentary")
        commentary_row = f"""
            <tr>
                <td colspan="3" style="padding:0 12px 10px 12px;color:#6b7280;font-size:12px;font-style:italic;">
                    {commentary}
                </td>
            </tr>""" if commentary else ""
        rows += f"""
            <tr style="border-top:1px solid #e2e8f0;">
                <td style="padding:10px 12px;font-weight:bold;">{r["ticker"]}</td>
                <td style="padding:10px 12px;{_rsi_style(r[alert_key])}">{_fmt(r[rsi_key])}</td>
                <td style="padding:10px 12px;">{_badge(r[alert_key])}</td>
            </tr>{commentary_row}"""

    return f"""
        <div style="margin:24px 0;">
            <h2 style="color:#1e40af;font-size:15px;margin-bottom:10px;">{title}</h2>
            <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px;overflow:hidden;">
                <thead>
                    <tr style="background:#e2e8f0;font-size:11px;text-transform:uppercase;color:#6b7280;">
                        <th style="padding:8px 12px;text-align:left;">Ticker</th>
                        <th style="padding:8px 12px;text-align:left;">RSI</th>
                        <th style="padding:8px 12px;text-align:left;">Signal</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>"""


def _watchlist_table(results: List[Dict]) -> str:
    rows = "".join(f"""
        <tr style="border-top:1px solid #e2e8f0;">
            <td style="padding:10px 12px;font-weight:bold;">{r["ticker"]}</td>
            <td style="padding:10px 12px;{_rsi_style(r["daily_alert"])}">{_fmt(r["daily_rsi"])}</td>
            <td style="padding:10px 12px;">{_badge(r["daily_alert"])}</td>
            <td style="padding:10px 12px;{_rsi_style(r["weekly_alert"])}">{_fmt(r["weekly_rsi"])}</td>
            <td style="padding:10px 12px;">{_badge(r["weekly_alert"])}</td>
        </tr>"""
        for r in results
    )
    return f"""
        <div style="margin:24px 0;">
            <h2 style="color:#1e40af;font-size:15px;margin-bottom:10px;">Full Watchlist</h2>
            <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px;overflow:hidden;">
                <thead>
                    <tr style="background:#e2e8f0;font-size:11px;text-transform:uppercase;color:#6b7280;">
                        <th style="padding:8px 12px;text-align:left;">Ticker</th>
                        <th style="padding:8px 12px;text-align:left;">Daily RSI</th>
                        <th style="padding:8px 12px;text-align:left;">Short-term</th>
                        <th style="padding:8px 12px;text-align:left;">Weekly RSI</th>
                        <th style="padding:8px 12px;text-align:left;">Long-term</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>"""


def build_html(results: List[Dict[str, Any]], summary: str) -> str:
    today = date.today().strftime("%B %d, %Y")
    total_alerts = sum(1 for r in results if r["daily_alert"] or r["weekly_alert"])
    alert_label = f"{total_alerts} alert{'s' if total_alerts != 1 else ''}" if total_alerts else "No alerts"

    short_term = [r for r in results if r["daily_alert"]]
    long_term = [r for r in results if r["weekly_alert"]]

    summary_block = f"""
        <div style="margin:24px 0;padding:16px;background:#eff6ff;border-left:4px solid #3b82f6;border-radius:4px;">
            <p style="margin:0;color:#1e40af;font-size:13px;">{summary}</p>
        </div>""" if summary else ""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;color:#111827;background:#ffffff;">

    <div style="background:#0f172a;color:white;padding:24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;letter-spacing:0.3px;">Stock Sentinel</h1>
        <p style="margin:6px 0 0;color:#94a3b8;font-size:13px;">
            {today}&nbsp;&nbsp;·&nbsp;&nbsp;{len(results)} stocks monitored&nbsp;&nbsp;·&nbsp;&nbsp;{alert_label}
        </p>
    </div>

    <div style="padding:0 24px 24px;">
        {summary_block}
        {_alert_section("⚡ Short-term Alerts (Daily RSI)", short_term, "daily_rsi", "daily_alert")}
        {_alert_section("📈 Long-term Alerts (Weekly RSI)", long_term, "weekly_rsi", "weekly_alert")}
        {_watchlist_table(results)}
    </div>

    <div style="background:#f1f5f9;padding:14px 24px;text-align:center;color:#9ca3af;font-size:11px;border-radius:0 0 8px 8px;">
        Stock Sentinel&nbsp;&nbsp;·&nbsp;&nbsp;Watch: RSI &lt; 35&nbsp;&nbsp;·&nbsp;&nbsp;Consider Buy: RSI &lt; 30&nbsp;&nbsp;·&nbsp;&nbsp;Not financial advice.
    </div>

</body>
</html>"""


def send(results: List[Dict[str, Any]], summary: str) -> None:
    today = date.today().strftime("%b %d, %Y")
    alert_count = sum(1 for r in results if r["daily_alert"] or r["weekly_alert"])
    subject = f"Stock Sentinel — {today}"
    if alert_count:
        subject += f" ({alert_count} alert{'s' if alert_count != 1 else ''})"

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

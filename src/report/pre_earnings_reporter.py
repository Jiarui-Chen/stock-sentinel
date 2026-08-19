"""
Builds and sends the pre-earnings historical pattern email.
"""

from __future__ import annotations

import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from src.config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS, SMTP_HOST, SMTP_PORT
from src.i18n import t, fmt_date_long, fmt_date_short


def _pct_cell(v: Optional[float]) -> str:
    if v is None:
        return '<td style="padding:8px 14px;text-align:right;font-size:12px;color:#9ca3af;">—</td>'
    sign  = "+" if v >= 0 else ""
    color = "#16a34a" if v >= 0 else "#dc2626"
    return (
        f'<td style="padding:8px 14px;text-align:right;font-size:12px;'
        f'font-weight:bold;color:{color};">{sign}{v*100:.1f}%</td>'
    )


def _avg(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _watch_points_block(points: Optional[List[str]]) -> str:
    if not points:
        return ""
    items = "".join(
        f'<li style="padding:5px 0;font-size:12px;color:#374151;line-height:1.6;">{p}</li>'
        for p in points
    )
    return f"""
        <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
            <div style="padding:10px 16px;background:#1e3a5f;">
                <span style="font-weight:bold;font-size:13px;color:#f8fafc;
                             letter-spacing:0.5px;">{t("pe_sec_watch")}</span>
            </div>
            <div style="padding:8px 16px 12px;">
                <ol style="margin:6px 0;padding-left:20px;">{items}</ol>
            </div>
        </div>"""


def build_html(
    ticker: str,
    upcoming_date: str,
    history: List[Dict[str, Any]],
    watch_points: Optional[List[str]] = None,
) -> str:
    today      = fmt_date_long(date.today())
    days_until = (date.fromisoformat(upcoming_date) - date.today()).days

    pre_vals  = [q["pre_return"]  for q in history]
    post_vals = [q["post_return"] for q in history]
    avg_pre   = _avg(pre_vals)
    avg_post  = _avg(post_vals)

    rows = ""
    for i, q in enumerate(history):
        bg = "#ffffff" if i % 2 == 0 else "#f9fafb"
        rows += (
            f'<tr style="background:{bg};border-top:1px solid #f1f5f9;">'
            f'<td style="padding:8px 14px;font-size:12px;color:#374151;">{q["earnings_date"]}</td>'
            + _pct_cell(q["pre_return"])
            + _pct_cell(q["post_return"])
            + "</tr>"
        )

    n = len(history)
    post_note = (
        t("pe_post_note", have=sum(1 for v in post_vals if v is not None), n=n)
        if any(v is None for v in post_vals) else ""
    )
    avg_row = (
        f'<tr style="background:#f0f4f8;border-top:2px solid #cbd5e1;">'
        f'<td style="padding:9px 14px;font-size:12px;font-weight:bold;color:#111827;">{t("pe_avg", n=n)}</td>'
        + _pct_cell(avg_pre)
        + _pct_cell(avg_post)
        + "</tr>"
    )

    watch_section = _watch_points_block(watch_points)
    days_html = f'<strong style="color:#111827;">{t("pe_days", n=days_until)}</strong>'
    intro     = t("pe_intro", edate=upcoming_date, days_html=days_html, n=n)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;
             color:#111827;background:#ffffff;">

    <div style="background:#0f172a;color:white;padding:22px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;letter-spacing:0.3px;">{t("pe_title", ticker=ticker)}</h1>
        <p style="margin:5px 0 0;color:#94a3b8;font-size:13px;">
            {t("pe_subtitle")} &nbsp;·&nbsp; {today}
        </p>
    </div>

    <div style="padding:16px 24px 28px;">

        <p style="font-size:13px;color:#374151;margin:0 0 16px;">
            {intro}
        </p>

        {watch_section}

        <div style="border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
            <div style="padding:10px 16px;background:#1e3a5f;">
                <span style="font-weight:bold;font-size:13px;color:#f8fafc;
                             letter-spacing:0.5px;">{t("pe_sec_history")}</span>
            </div>
            <table style="width:100%;border-collapse:collapse;">
                <tr style="background:#f8fafc;">
                    <td style="padding:7px 14px;font-size:10px;font-weight:bold;
                               color:#9ca3af;text-transform:uppercase;">{t("pe_col_date")}</td>
                    <td style="padding:7px 14px;font-size:10px;font-weight:bold;
                               color:#9ca3af;text-transform:uppercase;text-align:right;">
                               {t("pe_col_pre")}</td>
                    <td style="padding:7px 14px;font-size:10px;font-weight:bold;
                               color:#9ca3af;text-transform:uppercase;text-align:right;">
                               {t("pe_col_post")}{post_note}</td>
                </tr>
                {rows}
                {avg_row}
            </table>
        </div>

    </div>

    <div style="background:#f1f5f9;padding:12px 24px;text-align:center;
                color:#9ca3af;font-size:11px;border-radius:0 0 8px 8px;">
        {t("pe_footer")}
    </div>

</body>
</html>"""


def send(
    ticker: str,
    upcoming_date: str,
    history: List[Dict[str, Any]],
    watch_points: Optional[List[str]] = None,
) -> None:
    today   = fmt_date_short(date.today())
    subject = f'{t("pe_title", ticker=ticker)} · {today}'
    html    = build_html(ticker, upcoming_date, history, watch_points)

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = ", ".join(EMAIL_RECIPIENTS)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_SENDER, EMAIL_RECIPIENTS, msg.as_string())

    print(f"[OK] Pre-earnings email sent — {subject}")

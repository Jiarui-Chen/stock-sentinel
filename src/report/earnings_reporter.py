"""
Builds and sends the earnings call analysis email.
"""

from __future__ import annotations

import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from src.config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS, SMTP_HOST, SMTP_PORT


def _delta_span(val: Optional[float], is_margin: bool = False) -> str:
    """Render a QoQ/YoY delta with color and sign."""
    if val is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    color = "#16a34a" if val >= 0 else "#dc2626"
    sign  = "+" if val >= 0 else ""
    unit  = "pp" if is_margin else "%"
    return f'<span style="color:{color};font-weight:bold;">{sign}{val:.1f}{unit}</span>'


def _fmt_val(v: Optional[float]) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v:.2f}"


def _fmt_pct(v: Optional[float]) -> str:
    return f"{v:.1f}%" if v is not None else "—"


def _metrics_table(financials: Dict) -> str:
    if not financials:
        return '<p style="color:#9ca3af;font-size:12px;">财务数据暂不可用</p>'

    rows = [
        ("营收",       _fmt_val(financials.get("revenue")),      financials.get("revenue_qoq"),      financials.get("revenue_yoy"),      False),
        ("毛利率",     _fmt_pct(financials.get("gross_margin")), financials.get("gross_margin_qoq"), financials.get("gross_margin_yoy"), True),
        ("运营利润率", _fmt_pct(financials.get("op_margin")),    financials.get("op_margin_qoq"),    financials.get("op_margin_yoy"),    True),
        ("净利润",     _fmt_val(financials.get("net_income")),   financials.get("net_income_qoq"),   financials.get("net_income_yoy"),   False),
        ("EPS",        _fmt_val(financials.get("eps")),          financials.get("eps_qoq"),          financials.get("eps_yoy"),          False),
    ]

    header = (
        '<tr style="background:#f8fafc;">'
        '<td style="padding:7px 12px;font-size:10px;font-weight:bold;color:#9ca3af;text-transform:uppercase;">指标</td>'
        '<td style="padding:7px 12px;font-size:10px;font-weight:bold;color:#9ca3af;text-transform:uppercase;text-align:right;">本季度</td>'
        '<td style="padding:7px 12px;font-size:10px;font-weight:bold;color:#9ca3af;text-transform:uppercase;text-align:right;">QoQ</td>'
        '<td style="padding:7px 12px;font-size:10px;font-weight:bold;color:#9ca3af;text-transform:uppercase;text-align:right;">YoY</td>'
        '</tr>'
    )

    body = ""
    for label, value, qoq, yoy, is_margin in rows:
        body += (
            f'<tr style="border-top:1px solid #f1f5f9;">'
            f'<td style="padding:8px 12px;font-size:12px;color:#374151;">{label}</td>'
            f'<td style="padding:8px 12px;font-size:12px;font-weight:bold;color:#111827;text-align:right;">{value}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{_delta_span(qoq, is_margin)}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{_delta_span(yoy, is_margin)}</td>'
            f'</tr>'
        )

    period = financials.get("period", "")
    period_note = f'<p style="font-size:11px;color:#9ca3af;margin:4px 0 0;">报告期：{period}</p>' if period else ""

    return f"""
    <table style="width:100%;border-collapse:collapse;">
        {header}
        {body}
    </table>
    {period_note}"""


def _talking_points_block(points: List[str]) -> str:
    items = "".join(
        f'<li style="padding:4px 0;font-size:12px;color:#374151;line-height:1.6;">{p}</li>'
        for p in points
    )
    return f'<ul style="margin:8px 0;padding-left:18px;">{items}</ul>'


def _section(title: str, content: str) -> str:
    return f"""
    <div style="margin:16px 0;">
        <div style="font-size:10px;font-weight:bold;color:#9ca3af;text-transform:uppercase;
                    letter-spacing:0.5px;margin-bottom:8px;">{title}</div>
        {content}
    </div>"""


def build_html(ticker: str, analysis: Dict[str, Any], financials: Optional[Dict]) -> str:
    today = date.today().strftime("%B %d, %Y")

    metrics   = _metrics_table(financials or {})
    points    = _talking_points_block(analysis.get("key_talking_points") or [])
    highlights = f'<p style="font-size:12px;color:#374151;line-height:1.7;margin:0;">{analysis.get("financial_highlights", "")}</p>'
    outlook    = f'<p style="font-size:12px;color:#374151;line-height:1.7;margin:0;">{analysis.get("outlook_interpretation", "")}</p>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;max-width:660px;margin:0 auto;color:#111827;background:#ffffff;">

    <div style="background:#0f172a;color:white;padding:22px 24px;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:20px;letter-spacing:0.3px;">财报速递 · {ticker}</h1>
        <p style="margin:5px 0 0;color:#94a3b8;font-size:13px;">
            Earnings Call Analysis &nbsp;·&nbsp; {today}
        </p>
    </div>

    <div style="padding:8px 24px 28px;">

        <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
            <div style="padding:10px 16px;background:#1e3a5f;">
                <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">关键财务指标</span>
            </div>
            <div style="padding:4px 4px 8px;">
                {metrics}
            </div>
        </div>

        <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
            <div style="padding:10px 16px;background:#1e3a5f;">
                <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">财务亮点</span>
            </div>
            <div style="padding:12px 16px;">
                {highlights}
            </div>
        </div>

        <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
            <div style="padding:10px 16px;background:#1e3a5f;">
                <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">管理层核心观点</span>
            </div>
            <div style="padding:8px 16px;">
                {points}
            </div>
        </div>

        <div style="border:1px solid #e2e8f0;border-radius:6px;margin:16px 0;overflow:hidden;">
            <div style="padding:10px 16px;background:#1e3a5f;">
                <span style="font-weight:bold;font-size:13px;color:#f8fafc;letter-spacing:0.5px;">前景解读</span>
            </div>
            <div style="padding:12px 16px;">
                {outlook}
            </div>
        </div>

    </div>

    <div style="background:#f1f5f9;padding:12px 24px;text-align:center;color:#9ca3af;
                font-size:11px;border-radius:0 0 8px 8px;">
        数据来源：SEC EDGAR · yfinance · Not financial advice.
    </div>

</body>
</html>"""


def send(ticker: str, analysis: Dict[str, Any], financials: Optional[Dict]) -> None:
    today   = date.today().strftime("%b %d, %Y")
    subject = f"财报速递 · {ticker} · {today}"
    html    = build_html(ticker, analysis, financials)

    outer = MIMEMultipart("related")
    outer["Subject"] = subject
    outer["From"]    = EMAIL_SENDER
    outer["To"]      = ", ".join(EMAIL_RECIPIENTS)
    outer.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_SENDER, EMAIL_RECIPIENTS, outer.as_string())

    print(f"[OK] Earnings report sent — {subject}")

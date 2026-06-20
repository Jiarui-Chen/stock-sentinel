import base64
import struct
import zlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import date
from typing import Dict, List, Any, Optional, Tuple
from src.config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_HOST, SMTP_PORT

_CHART_POINTS = 21


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


def _macd_chart_png(macd_series: list, signal_series: list, hist_series: list) -> bytes:
    """Returns raw PNG bytes for the MACD chart using only stdlib. Returns b'' if data insufficient."""
    ms = macd_series[-_CHART_POINTS:]
    ss = signal_series[-_CHART_POINTS:]
    hs = hist_series[-_CHART_POINTS:]
    n  = len(hs)
    if n < 2 or len(ms) < 2 or len(ss) < 2:
        return b""

    W, H = 300, 80
    pad_x, pad_y = 8, 6
    cw = W - 2 * pad_x
    ch = H - 2 * pad_y
    bar_w = cw / n

    all_vals = ms + ss + hs
    y_min = min(all_vals)
    y_max = max(all_vals)
    y_rng = y_max - y_min or 1.0

    def v2y(v: float) -> int:
        return max(pad_y, min(H - pad_y - 1, int(pad_y + ch * (1.0 - (v - y_min) / y_rng))))

    def i2x(i: int) -> int:
        return int(pad_x + (i + 0.5) * bar_w)

    canvas = bytearray([255] * (W * H * 3))

    def set_px(x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < W and 0 <= y < H:
            idx = (y * W + x) * 3
            canvas[idx], canvas[idx + 1], canvas[idx + 2] = r, g, b

    zero_y = v2y(0)

    for i, h in enumerate(hs):
        x0 = int(pad_x + i * bar_w) + 2
        x1 = int(pad_x + (i + 1) * bar_w) - 2
        r, g, b = (134, 239, 172) if h >= 0 else (252, 165, 165)
        top, bot = sorted([v2y(h), zero_y])
        for yi in range(top, bot + 1):
            for xi in range(x0, x1 + 1):
                set_px(xi, yi, r, g, b)

    x = pad_x
    while x < W - pad_x:
        for xi in range(x, min(x + 4, W - pad_x)):
            set_px(xi, zero_y, 209, 213, 219)
        x += 8

    def draw_line(x0: int, y0: int, x1: int, y1: int, r: int, g: int, b: int) -> None:
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            set_px(x0, y0,     r, g, b)
            set_px(x0, y0 - 1, r, g, b)
            set_px(x0, y0 + 1, r, g, b)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    for i in range(n - 1):
        draw_line(i2x(i), v2y(ms[i]), i2x(i + 1), v2y(ms[i + 1]), 59, 130, 246)
    for i in range(n - 1):
        draw_line(i2x(i), v2y(ss[i]), i2x(i + 1), v2y(ss[i + 1]), 249, 115, 22)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw.extend(canvas[y * W * 3:(y + 1) * W * 3])

    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def _label_cell(text: str) -> str:
    return (
        f'<td style="padding:9px 12px 9px 16px;color:#9ca3af;font-size:10px;font-weight:bold;'
        f'text-transform:uppercase;white-space:nowrap;vertical-align:top;width:64px;">{text}</td>'
    )


def _timeframe_row(
    label: str, ticker: str,
    rsi_val: str, rsi_alert: Optional[str], div: Optional[str],
    macd_series: list, signal_series: list, hist_series: list,
    hist_sign: Optional[str], hist_momentum: Optional[str],
    charts: Dict[str, bytes],
    border_top: bool = True,
) -> str:
    border = "border-top:1px solid #f1f5f9;" if border_top else ""

    div_html = ""
    if div:
        col = "#16a34a" if div == "bullish" else "#dc2626"
        div_html = f' &nbsp;<span style="color:{col};font-weight:bold;font-size:11px;">{div.upper()} DIV</span>'

    cid = f"macd_{ticker}_{label.lower()}"
    png = _macd_chart_png(macd_series, signal_series, hist_series)
    if png:
        charts[cid] = png
        chart_div = f'<div style="margin-top:6px;"><img src="cid:{cid}" width="300" style="width:100%;max-width:300px;height:auto;display:block;" alt=""/></div>'
    else:
        chart_div = ""

    return f"""
        <tr style="{border}">
            {_label_cell(label)}
            <td style="padding:9px 16px 8px;font-size:12px;">
                RSI {_rsi_span(rsi_val, rsi_alert)}{div_html}
                {chart_div}
                <div style="font-size:10px;color:#6b7280;margin-top:3px;">
                    MACD Hist {_macd_hist_span(hist_sign, hist_momentum)}
                    <span style="margin-left:10px;color:#3b82f6;">&#9644; MACD</span>
                    <span style="margin-left:6px;color:#f97316;">&#9644; Signal</span>
                </div>
            </td>
        </tr>"""


def _ticker_card(r: Dict, charts: Dict[str, bytes]) -> str:
    rows = ""

    if r.get("news_summary"):
        sentiment  = r.get("news_sentiment") or ""
        sent_color = {"bullish": "#16a34a", "bearish": "#dc2626"}.get(sentiment, "#6b7280")
        sent_label = f'<span style="color:{sent_color};font-weight:bold;">{sentiment.upper()}</span>  ' if sentiment else ""
        implication = r.get("news_implication") or ""
        impl = f'<div style="color:#6b7280;margin-top:3px;">{implication}</div>' if implication else ""
        rows += f"""
            <tr>
                {_label_cell("News")}
                <td style="padding:9px 16px;font-size:12px;color:#374151;">{sent_label}{r["news_summary"]}{impl}</td>
            </tr>"""

    rows += _timeframe_row(
        label="Daily", ticker=r["ticker"],
        rsi_val=_fmt(r.get("daily_rsi")), rsi_alert=r.get("daily_alert"),
        div=r.get("daily_rsi_divergence"),
        macd_series=r.get("daily_macd_series", []),
        signal_series=r.get("daily_signal_series", []),
        hist_series=r.get("daily_hist_series", []),
        hist_sign=r.get("daily_macd_hist_sign"),
        hist_momentum=r.get("daily_macd_hist_momentum"),
        charts=charts,
        border_top=bool(r.get("news_summary")),
    )

    rows += _timeframe_row(
        label="Weekly", ticker=r["ticker"],
        rsi_val=_fmt(r.get("weekly_rsi")), rsi_alert=r.get("weekly_alert"),
        div=r.get("weekly_rsi_divergence"),
        macd_series=r.get("weekly_macd_series", []),
        signal_series=r.get("weekly_signal_series", []),
        hist_series=r.get("weekly_hist_series", []),
        hist_sign=r.get("weekly_macd_hist_sign"),
        hist_momentum=r.get("weekly_macd_hist_momentum"),
        charts=charts,
        border_top=True,
    )

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
    has_div  = 0 if (r.get("daily_rsi_divergence") or r.get("weekly_rsi_divergence")) else 1
    has_news = 0 if r.get("news_summary") else 1
    return (alert_rank, has_div, has_news)


def build_html(results: List[Dict[str, Any]], summary: str) -> Tuple[str, Dict[str, bytes]]:
    """Returns (html_string, {cid: png_bytes}) for CID-embedded chart images."""
    charts: Dict[str, bytes] = {}
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

    ticker_cards = "".join(_ticker_card(r, charts) for r in sorted(results, key=_sort_key))

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
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

    return html, charts


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

    html, charts = build_html(results, summary)

    # MIMEMultipart("related") allows CID-referenced inline images
    outer = MIMEMultipart("related")
    outer["Subject"] = subject
    outer["From"]    = EMAIL_SENDER
    outer["To"]      = EMAIL_RECIPIENT
    outer.attach(MIMEText(html, "html"))

    for cid, png_bytes in charts.items():
        img = MIMEImage(png_bytes, "png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline")
        outer.attach(img)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, outer.as_string())

    print(f"[OK] Report sent — {subject} ({len(charts)} chart images attached)")

"""
Analyzes an earnings call transcript using Claude Sonnet.

Extracts: key financial metrics summary, executive talking points, and
forward-looking interpretation — all written in Chinese (简体中文).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SMART

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
你是一名专业的股票分析师，专注于解读上市公司的财报信息。

你将收到：
1. 该公司最新季度的关键财务指标（含环比QoQ和同比YoY变化）
2. SEC EDGAR 8-K 文件内容（可能是完整的财报电话会议记录，也可能是财报新闻稿/业绩公告）

你的任务是用简体中文输出以下三部分内容：

**财务亮点**：概括本季度最重要的财务表现（营收、毛利率、运营利润率、EPS），重点指出哪些指标超预期/低于预期，以及环比/同比的关键变化。2-4句话。

**管理层核心观点**：提炼管理层（CEO/CFO）在文件中提到的3-5个最重要的战略/业务观点，每条用一句话概括。只关注有实质内容的观点，跳过套话和客套。

**前景解读**：基于管理层的表态和财务数据，分析这对公司未来2-4个季度的业务走向意味着什么。重点关注：收入增长驱动力、利润率趋势、潜在风险。3-5句话。

输出要简洁、具体、有洞察力。避免泛泛而谈。\
"""

_TOOL = {
    "name": "report_earnings_analysis",
    "description": "Report the structured earnings analysis in Chinese.",
    "input_schema": {
        "type": "object",
        "properties": {
            "financial_highlights": {
                "type": "string",
                "description": "财务亮点 — 2-4 sentences in Chinese",
            },
            "key_talking_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "管理层核心观点 — list of 3-5 concise points in Chinese",
            },
            "outlook_interpretation": {
                "type": "string",
                "description": "前景解读 — 3-5 sentences in Chinese",
            },
        },
        "required": ["financial_highlights", "key_talking_points", "outlook_interpretation"],
    },
}

# Transcript is often very long; send only the first ~12,000 chars to stay within limits
# while preserving the prepared remarks (most valuable section)
_MAX_TRANSCRIPT_CHARS = 12_000


def analyze(ticker: str, financials: Optional[Dict], transcript: str) -> Optional[Dict[str, Any]]:
    """
    Returns {financial_highlights, key_talking_points, outlook_interpretation}
    or None on failure.
    """
    fin_summary = _format_financials(financials) if financials else "财务数据暂不可用。"
    truncated   = transcript[:_MAX_TRANSCRIPT_CHARS]
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        truncated += "\n\n[记录已截断]"

    user_content = (
        f"公司：{ticker}\n\n"
        f"## 关键财务指标\n{fin_summary}\n\n"
        f"## SEC EDGAR 8-K 财报文件\n{truncated}"
    )

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL_SMART,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_earnings_analysis"},
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )
        raw = next(b for b in response.content if b.type == "tool_use").input
        if isinstance(raw, str):
            raw = json.loads(raw)
        return raw
    except Exception as e:
        print(f"[WARN] [{ticker}] Earnings analysis failed: {e}")
        return None


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _fmt_pp(v: Optional[float]) -> str:
    """Format a percentage-point delta (margins QoQ/YoY)."""
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}pp"


def _fmt_val(v: Optional[float], unit: str = "") -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1e9:
        return f"{v/1e9:.2f}B{unit}"
    if abs(v) >= 1e6:
        return f"{v/1e6:.1f}M{unit}"
    return f"{v:.2f}{unit}"


def _format_financials(f: Dict) -> str:
    lines = [f"报告期：{f.get('period', 'N/A')}"]
    lines.append(
        f"营收：{_fmt_val(f.get('revenue'))}  "
        f"QoQ {_fmt_pct(f.get('revenue_qoq'))}  "
        f"YoY {_fmt_pct(f.get('revenue_yoy'))}"
    )
    lines.append(
        f"毛利率：{_fmt_pct(f.get('gross_margin'))}  "
        f"QoQ {_fmt_pp(f.get('gross_margin_qoq'))}  "
        f"YoY {_fmt_pp(f.get('gross_margin_yoy'))}"
    )
    lines.append(
        f"运营利润率：{_fmt_pct(f.get('op_margin'))}  "
        f"QoQ {_fmt_pp(f.get('op_margin_qoq'))}  "
        f"YoY {_fmt_pp(f.get('op_margin_yoy'))}"
    )
    lines.append(
        f"净利润：{_fmt_val(f.get('net_income'))}  "
        f"QoQ {_fmt_pct(f.get('net_income_qoq'))}  "
        f"YoY {_fmt_pct(f.get('net_income_yoy'))}"
    )
    lines.append(
        f"EPS：{_fmt_val(f.get('eps'))}  "
        f"QoQ {_fmt_pct(f.get('eps_qoq'))}  "
        f"YoY {_fmt_pct(f.get('eps_yoy'))}"
    )
    return "\n".join(lines)

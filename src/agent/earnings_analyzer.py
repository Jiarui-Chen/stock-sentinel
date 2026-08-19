"""
Analyzes an earnings call transcript using Claude Sonnet.

Extracts: key financial metrics summary, executive talking points, and
forward-looking interpretation — written in the language set by REPORT_LANGUAGE.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SMART
from src.i18n import prompt_language_directive

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Leading list marker: a bullet or an enumerator like "1." / "2)" / "3、".
_ENUM_PREFIX = re.compile(r"^\s*(?:[-*•·]|\d+[.)、．）])\s*")


def _normalize_points(value: Any) -> List[str]:
    """
    Coerce a list-typed analysis field into a clean list of strings.

    Claude's tool output occasionally returns an array field (key_talking_points,
    watch_point_responses) as a single string instead of a list — a lone point, a
    JSON-encoded array, or a newline/numbered blob. Rendering code that iterates
    the value would then walk it one character per bullet (e.g. 财/报/结/果), so we
    normalize to a real list here. A twin of this helper guards the renderer in
    src/report/earnings_reporter.py.
    """
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        # A JSON-encoded array, e.g. '["点一", "点二"]'.
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    value = parsed
            except ValueError:
                pass
        # Still a string → split a newline/numbered blob into separate points.
        if isinstance(value, str):
            value = [_ENUM_PREFIX.sub("", ln) for ln in s.splitlines()]
    if not isinstance(value, list):
        value = [value]
    return [str(p).strip() for p in value if p is not None and str(p).strip()]

_SYSTEM_PROMPT = """\
You are a professional equity analyst who interprets quarterly earnings disclosures.

Your reader is a long-term investor with a 6-18 month holding horizon who does not trade
short term. Your interpretation must therefore answer "how does this report change the
company's operating trajectory over the next 6-18 months?", NOT "where does the stock go
after the print?". Focus on structural changes — durability of revenue growth, margin
direction, competitive position, capex and cash flow — and ignore noise that only affects
the earnings-day reaction.

You are given:
1. The company's key financial metrics for the latest quarter (with QoQ and YoY changes)
2. SEC EDGAR 8-K content (either a full earnings call transcript, or an earnings press release)
3. (If available) the 5 watch points raised before the report

Produce the following:

**Financial highlights** (financial_highlights): Summarize the quarter's most important results
(revenue, gross margin, operating margin, EPS), calling out which metrics beat or missed and the
key QoQ/YoY moves. 2-4 sentences.

**Management takeaways** (key_talking_points): Extract the 3-5 most important strategic or
operational points management (CEO/CFO) made. One sentence each. Keep only points with real
substance — skip boilerplate and pleasantries.

**Outlook** (outlook_interpretation): Based on management's commentary and the financials, analyze
what this means for the business over the next 6-18 months (roughly 2-6 quarters). Focus on whether
the growth drivers are durable, the margin trend, shifts in competitive position, and risks that
could break the long-term thesis. State explicitly whether this quarter's changes look structural
or one-off. 3-5 sentences.

**Pre-earnings review** (watch_point_responses, only when watch points are supplied): Answer each
watch point in the original order, one sentence each, explaining how this report addressed it —
delivered, beat expectations, or disappointed.

Be concise, specific and insightful. Avoid generalities, and never predict short-term price moves.\
"""


def _build_tool(with_watch_points: bool) -> dict:
    props: dict = {
        "financial_highlights": {
            "type": "string",
            "description": "Financial highlights — 2-4 sentences",
        },
        "key_talking_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Management takeaways — list of 3-5 concise points",
        },
        "outlook_interpretation": {
            "type": "string",
            "description": "Outlook — 3-5 sentences",
        },
    }
    required = ["financial_highlights", "key_talking_points", "outlook_interpretation"]

    if with_watch_points:
        props["watch_point_responses"] = {
            "type": "array",
            "items": {"type": "string"},
            "description": "Pre-earnings review — one sentence per watch point, in the same order",
        }
        required.append("watch_point_responses")

    return {
        "name": "report_earnings_analysis",
        "description": "Report the structured earnings analysis.",
        "input_schema": {"type": "object", "properties": props, "required": required},
    }

# Transcript is often very long; send only the first ~12,000 chars to stay within limits
# while preserving the prepared remarks (most valuable section)
_MAX_TRANSCRIPT_CHARS = 12_000


def analyze(
    ticker: str,
    financials: Optional[Dict],
    transcript: str,
    watch_points: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Returns {financial_highlights, key_talking_points, outlook_interpretation}
    and optionally watch_point_responses when watch_points are supplied.
    Returns None on failure.
    """
    fin_summary = _format_financials(financials) if financials else "Financial data unavailable."
    truncated   = transcript[:_MAX_TRANSCRIPT_CHARS]
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        truncated += "\n\n[transcript truncated]"

    user_content = (
        f"Company: {ticker}\n\n"
        f"## Key financial metrics\n{fin_summary}\n\n"
        f"## SEC EDGAR 8-K filing\n{truncated}"
    )

    if watch_points:
        numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(watch_points))
        user_content += (
            "\n\n## Pre-earnings watch points "
            f"(answer each in order in watch_point_responses)\n{numbered}"
        )

    tool = _build_tool(bool(watch_points))

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL_SMART,
            max_tokens=2048,
            tools=[tool],
            tool_choice={"type": "tool", "name": "report_earnings_analysis"},
            system=[{"type": "text", "text": _SYSTEM_PROMPT + prompt_language_directive(),
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )
        raw = next(b for b in response.content if b.type == "tool_use").input
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            # These are declared as arrays in the tool schema, but tool-use input
            # isn't type-enforced — coerce them so the renderer never iterates a
            # bare string character-by-character.
            raw["key_talking_points"] = _normalize_points(raw.get("key_talking_points"))
            if "watch_point_responses" in raw:
                raw["watch_point_responses"] = _normalize_points(raw.get("watch_point_responses"))
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
    lines = [f"Period: {f.get('period', 'N/A')}"]
    lines.append(
        f"Revenue: {_fmt_val(f.get('revenue'))}  "
        f"QoQ {_fmt_pct(f.get('revenue_qoq'))}  "
        f"YoY {_fmt_pct(f.get('revenue_yoy'))}"
    )
    lines.append(
        f"Gross margin: {_fmt_pct(f.get('gross_margin'))}  "
        f"QoQ {_fmt_pp(f.get('gross_margin_qoq'))}  "
        f"YoY {_fmt_pp(f.get('gross_margin_yoy'))}"
    )
    lines.append(
        f"Operating margin: {_fmt_pct(f.get('op_margin'))}  "
        f"QoQ {_fmt_pp(f.get('op_margin_qoq'))}  "
        f"YoY {_fmt_pp(f.get('op_margin_yoy'))}"
    )
    lines.append(
        f"Net income: {_fmt_val(f.get('net_income'))}  "
        f"QoQ {_fmt_pct(f.get('net_income_qoq'))}  "
        f"YoY {_fmt_pct(f.get('net_income_yoy'))}"
    )
    lines.append(
        f"EPS: {_fmt_val(f.get('eps'))}  "
        f"QoQ {_fmt_pct(f.get('eps_qoq'))}  "
        f"YoY {_fmt_pct(f.get('eps_yoy'))}"
    )
    return "\n".join(lines)

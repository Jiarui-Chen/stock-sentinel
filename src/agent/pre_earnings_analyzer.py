"""
Generates 5 watch points for an upcoming earnings call using Claude Haiku.
Input: historical pre/post return pattern, recent quarterly financials, news headlines.
Output: 5 concise sentences in the language set by REPORT_LANGUAGE.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.i18n import prompt_language_directive

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM = """\
You are an equity researcher covering earnings season for a long-term investor with a
6-18 month holding horizon.

The watch points you produce must target "which long-term theses will this report confirm or
break" — durability of revenue growth, margin trend, execution against new business lines,
competitive position, and guidance changes. Do NOT raise short-term questions that only concern
the earnings-day move (e.g. "will it gap", "what is implied volatility"). The historical pre/post
price pattern is background on market expectations, never a watch point in itself.

You are given:
1. How this stock has moved before and after its earnings over the past several quarters
2. Key financial metrics for the most recent quarter (with QoQ/YoY changes)
3. Recent related news headlines

You may also use the web_search tool to look up the latest analyst estimates, market consensus,
recent developments, or anything else that supplements the data provided.

Based on all of the above, distill the 5 most important things to watch in this earnings report.
Each point should focus on one concrete question, risk, or opportunity, in a single sentence — no
generalities — and should make clear what it means for the next 6-18 months of the business.

When you are done, submit your 5 points using the report_watch_points tool.\
"""


_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}

_TOOL = {
    "name": "report_watch_points",
    "description": "Report the 5 watch points for the upcoming earnings call.",
    "input_schema": {
        "type": "object",
        "properties": {
            "point_1": {"type": "string"},
            "point_2": {"type": "string"},
            "point_3": {"type": "string"},
            "point_4": {"type": "string"},
            "point_5": {"type": "string"},
        },
        "required": ["point_1", "point_2", "point_3", "point_4", "point_5"],
    },
}


def _fmt_history(history: List[Dict]) -> str:
    lines = ["Earnings date   Prior 10d   Next 10d"]
    for q in history:
        pre  = f'{q["pre_return"]*100:+.1f}%'
        post = f'{q["post_return"]*100:+.1f}%' if q["post_return"] is not None else "N/A"
        lines.append(f'{q["earnings_date"]}   {pre:>9}  {post:>9}')
    return "\n".join(lines)


def _fmt_financials(f: Dict) -> str:
    def pct(v): return f"{v:+.1f}%" if v is not None else "N/A"
    def pp(v):  return f"{v:+.1f}pp" if v is not None else "N/A"
    def val(v):
        if v is None: return "N/A"
        if abs(v) >= 1e9: return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
        return f"${v:.2f}"
    return "\n".join([
        f"Period: {f.get('period', 'N/A')}",
        f"Revenue: {val(f.get('revenue'))}  QoQ {pct(f.get('revenue_qoq'))}  YoY {pct(f.get('revenue_yoy'))}",
        f"Gross margin: {pct(f.get('gross_margin'))}  QoQ {pp(f.get('gross_margin_qoq'))}  YoY {pp(f.get('gross_margin_yoy'))}",
        f"Operating margin: {pct(f.get('op_margin'))}  QoQ {pp(f.get('op_margin_qoq'))}  YoY {pp(f.get('op_margin_yoy'))}",
        f"Net income: {val(f.get('net_income'))}  QoQ {pct(f.get('net_income_qoq'))}  YoY {pct(f.get('net_income_yoy'))}",
        f"EPS: {val(f.get('eps'))}  QoQ {pct(f.get('eps_qoq'))}  YoY {pct(f.get('eps_yoy'))}",
    ])


def _fmt_news(articles: List[Dict]) -> str:
    if not articles:
        return "(no recent news)"
    return "\n".join(f"- {a['title']}" for a in articles[:8])


def analyze(
    ticker: str,
    history: List[Dict],
    financials: Optional[Dict],
    news_articles: List[Dict],
) -> Optional[List[str]]:
    """
    Returns a list of 5 Chinese watch-point strings, or None on failure.
    """
    hist_text = _fmt_history(history)
    fin_text  = _fmt_financials(financials) if financials else "(financial data unavailable)"
    news_text = _fmt_news(news_articles)

    user_msg = (
        f"Company: {ticker}\n\n"
        f"## Historical earnings price pattern\n{hist_text}\n\n"
        f"## Most recent quarterly metrics\n{fin_text}\n\n"
        f"## Recent news\n{news_text}"
    )

    tools = [_WEB_SEARCH_TOOL, _TOOL]
    messages = [{"role": "user", "content": user_msg}]

    try:
        for _ in range(5):
            resp = _client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                tools=tools,
                tool_choice={"type": "auto"},
                system=_SYSTEM + prompt_language_directive(),
                messages=messages,
            )

            for block in resp.content:
                if block.type == "tool_use" and block.name == "report_watch_points":
                    raw = block.input
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    return [raw[f"point_{i}"] for i in range(1, 6)]

            if resp.stop_reason == "pause_turn":
                # Server-side tool loop hit its iteration limit; re-submit to resume.
                messages = [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": resp.content},
                ]
                continue

            if resp.stop_reason == "end_turn":
                # Claude responded in text but didn't call report_watch_points; nudge it.
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({
                    "role": "user",
                    "content": "Please submit your 5 watch points using the report_watch_points tool.",
                })
                continue

            break  # unexpected stop_reason

        print(f"[WARN] [{ticker}] Pre-earnings analysis exhausted iterations without result.")
        return None
    except Exception as e:
        print(f"[WARN] [{ticker}] Pre-earnings analysis failed: {e}")
        return None

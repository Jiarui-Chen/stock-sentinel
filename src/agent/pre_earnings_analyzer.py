"""
Generates 5 watch points for an upcoming earnings call using Claude Haiku.
Input: historical pre/post return pattern, recent quarterly financials, news headlines.
Output: 5 concise Chinese sentences.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM = """\
你是一名专注于财报季的股票研究员。你将收到：
1. 该股票过去数季度财报前后的价格变动规律
2. 最近一季度的关键财务指标（含环比变化）
3. 近期相关新闻标题

你还可以使用 web_search 工具主动搜索该公司最新的分析师预期、市场共识、近期动态或其他相关信息，以补充系统提供的数据。

请根据以上所有信息，用简体中文提炼出本次财报最值得关注的 5 个要点。
每条要点聚焦一个具体问题或风险/机会，一句话概括，不要泛泛而谈。
分析完毕后，请使用 report_watch_points 工具提交你的 5 个要点。\
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
    lines = ["财报日期        前10交易日  后10交易日"]
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
        f"报告期：{f.get('period', 'N/A')}",
        f"营收：{val(f.get('revenue'))}  QoQ {pct(f.get('revenue_qoq'))}  YoY {pct(f.get('revenue_yoy'))}",
        f"毛利率：{pct(f.get('gross_margin'))}  QoQ {pp(f.get('gross_margin_qoq'))}  YoY {pp(f.get('gross_margin_yoy'))}",
        f"运营利润率：{pct(f.get('op_margin'))}  QoQ {pp(f.get('op_margin_qoq'))}  YoY {pp(f.get('op_margin_yoy'))}",
        f"净利润：{val(f.get('net_income'))}  QoQ {pct(f.get('net_income_qoq'))}  YoY {pct(f.get('net_income_yoy'))}",
        f"EPS：{val(f.get('eps'))}  QoQ {pct(f.get('eps_qoq'))}  YoY {pct(f.get('eps_yoy'))}",
    ])


def _fmt_news(articles: List[Dict]) -> str:
    if not articles:
        return "（无近期新闻）"
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
    fin_text  = _fmt_financials(financials) if financials else "（财务数据暂不可用）"
    news_text = _fmt_news(news_articles)

    user_msg = (
        f"公司：{ticker}\n\n"
        f"## 历史财报价格规律\n{hist_text}\n\n"
        f"## 最近季度财务指标\n{fin_text}\n\n"
        f"## 近期新闻\n{news_text}"
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
                system=_SYSTEM,
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
                    "content": "请使用 report_watch_points 工具提交你的 5 个要点。",
                })
                continue

            break  # unexpected stop_reason

        print(f"[WARN] [{ticker}] Pre-earnings analysis exhausted iterations without result.")
        return None
    except Exception as e:
        print(f"[WARN] [{ticker}] Pre-earnings analysis failed: {e}")
        return None

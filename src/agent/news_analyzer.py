import json
from typing import Any, Dict, List

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a strict stock news summarizer. Your ONLY source of truth is the article titles and summaries provided.

Rules you must never break:
- Before summarizing a ticker, verify that at least one article explicitly names or clearly refers to the company behind that ticker as its PRIMARY subject
- If you cannot confirm the articles are about that specific ticker's company, SKIP the ticker entirely — do not guess, do not infer, do not summarize
- If an article is primarily about a DIFFERENT company, IGNORE that article entirely
- ONLY report facts explicitly stated in the provided titles and summaries
- NEVER infer, extrapolate, or fill in details not present in the source material
- NEVER fabricate numbers, names, events, or outcomes
- If the source is vague, your output must be equally vague — do not guess at meaning
- If there is too little information to draw a meaningful implication, omit the implication field

For each ticker that has at least one article where that company is the PRIMARY subject:
1. Summarize in 1-2 sentences in Chinese using ONLY what is explicitly stated about THAT company
2. Set sentiment based strictly on the reported facts: "bullish", "bearish", "neutral", or "mixed"
3. Write a 1-sentence implication in Chinese grounded in the specific reported facts, if supported

Only include tickers you can confirm. Omit all others.\
"""

_TOOL = {
    "name": "report_news_analysis",
    "description": "Report news analysis results. Return an object where each key is a confirmed ticker symbol and the value is its analysis. Omit tickers with no confirmed articles.",
    "input_schema": {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "properties": {
                "confirmed":   {"type": "boolean", "description": "true only if at least one article is primarily about this ticker's company"},
                "sentiment":   {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
                "summary":     {"type": "string"},
                "implication": {"type": "string"},
            },
            "required": ["confirmed", "sentiment", "summary"],
        },
    },
}


def analyze(ticker_articles: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    """Returns {ticker: {news_sentiment, news_summary, news_implication}} for notable tickers."""
    active = {t: articles for t, articles in ticker_articles.items() if articles}
    if not active:
        return {}

    payload = json.dumps(
        [{"ticker": t, "articles": articles} for t, articles in active.items()],
        indent=2,
    )

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_news_analysis"},
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": f"Analyze these news articles:\n\n{payload}"}],
        )

        raw = next(b for b in response.content if b.type == "tool_use").input
        if isinstance(raw, str):
            raw = json.loads(raw)

        return {
            ticker: {
                "news_sentiment":   data.get("sentiment"),
                "news_summary":     data.get("summary"),
                "news_implication": data.get("implication"),
            }
            for ticker, data in raw.items()
            if isinstance(data, dict) and data.get("confirmed") is True
        }

    except Exception as e:
        print(f"[WARN] News analysis failed ({e}) — skipping news section.")
        return {}

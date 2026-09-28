import json
from typing import Any, Dict, List

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.i18n import prompt_language_directive
from src import degradation

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_BATCH_SIZE = 1  # tickers per API call

_SYSTEM_PROMPT = """\
You are a stock news summarizer serving a long-term investor with a 6-18 month holding horizon.

Judge everything by whether it changes the company's business trajectory over the next 6-18 months —
not by whether it moves the stock this week.

Your job:
1. Read the articles for each ticker and extract any content that directly mentions or concerns that specific company
2. Summarize what you find in 1-2 sentences
3. Set sentiment based on what is reported: "bullish", "bearish", "neutral", or "mixed"
4. Write a 1-sentence implication, if the content supports one
5. Score importance 1-10: how much this news should matter to an investor holding this stock for the next 6-18 months. Score high for anything that changes the multi-quarter trajectory — guidance changes, structural demand shifts, major partnerships or contracts, regulatory action, capital allocation, executive changes, competitive-position changes. Score low for anything that only affects the next few sessions — routine analyst price-target tweaks, daily price commentary, short-term momentum pieces, or recycled old news. Judge each ticker independently — do not try to rank tickers against each other.

Rules:
- ONLY use facts explicitly stated in the provided titles and summaries — never infer or fabricate
- Focus only on what the articles say about THAT specific company; ignore content about other companies
- If none of the articles contain anything directly about that company, omit that ticker from your response
- If there is too little information to draw a meaningful implication, omit the implication field
- The implication must address the 6-18 month outlook (demand, margins, competitive position, execution risk), not the near-term stock reaction\
"""

_TOOL = {
    "name": "report_news_analysis",
    "description": "Report news summaries. Return an object where each key is a ticker symbol and the value is its news summary. Only include tickers whose articles contain content directly about that company. Omit tickers where none of the articles mention that company.",
    "input_schema": {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "properties": {
                "sentiment":   {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
                "summary":     {"type": "string"},
                "implication": {"type": "string"},
                "importance":  {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["sentiment", "summary", "importance"],
        },
    },
}


def _analyze_batch(batch: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    payload = json.dumps(
        [{"ticker": t, "articles": articles} for t, articles in batch.items()],
        indent=2,
    )
    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "report_news_analysis"},
        system=[{"type": "text", "text": _SYSTEM_PROMPT + prompt_language_directive(),
                 "cache_control": {"type": "ephemeral"}}],
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
            "news_importance":  data.get("importance"),
        }
        for ticker, data in raw.items()
        if isinstance(data, dict) and data.get("summary")
    }


def analyze(ticker_articles: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    """Returns {ticker: {news_sentiment, news_summary, news_implication, news_importance}} for tickers with relevant news."""
    active = {t: articles for t, articles in ticker_articles.items() if articles}
    if not active:
        return {}

    results: Dict[str, Any] = {}
    items = list(active.items())

    for i in range(0, len(items), _BATCH_SIZE):
        batch = dict(items[i:i + _BATCH_SIZE])
        try:
            batch_results = _analyze_batch(batch)
            results.update(batch_results)
        except Exception as e:
            print(f"[WARN] News analysis failed for batch {list(batch.keys())}: {e}")
            degradation.record("news", e)

    return results

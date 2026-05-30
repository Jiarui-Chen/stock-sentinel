import json
from typing import Any, Dict, List

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a stock market news analyst. Given recent news headlines about specific stocks from the past 24 hours, analyze each ticker's news flow.

For each ticker with substantive investment-relevant news:
1. Summarize in 1-2 sentences (in Chinese) what the key news stories are about
2. Set sentiment to one of: "bullish", "bearish", "neutral", "mixed"
3. Write a 1-sentence investment implication (in Chinese) based on the news

Skip tickers with no headlines or only generic market noise unrelated to the company.

Respond ONLY with valid JSON matching this schema exactly:
{
  "tickers": [
    {
      "ticker": "AAPL",
      "sentiment": "bullish",
      "summary": "1-2 sentence summary of news",
      "implication": "1 sentence investment implication"
    }
  ]
}
"""


def analyze(ticker_headlines: Dict[str, List[str]]) -> Dict[str, Any]:
    """Returns {ticker: {news_sentiment, news_summary, news_implication}} for notable tickers."""
    active = {t: headlines for t, headlines in ticker_headlines.items() if headlines}
    if not active:
        return {}

    payload = json.dumps(
        [{"ticker": t, "headlines": headlines} for t, headlines in active.items()],
        indent=2,
    )

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": f"Analyze these news headlines:\n\n{payload}"}],
        )

        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        parsed = json.loads(raw)

        return {
            t["ticker"]: {
                "news_sentiment":   t.get("sentiment"),
                "news_summary":     t.get("summary"),
                "news_implication": t.get("implication"),
            }
            for t in parsed.get("tickers", [])
        }

    except Exception as e:
        print(f"[WARN] News analysis failed ({e}) — skipping news section.")
        return {}

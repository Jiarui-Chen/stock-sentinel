import json
import anthropic
from typing import List, Dict, Any, Tuple
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a concise stock technical analysis assistant focused on RSI signals.

Given a watchlist of stocks with their computed RSI values and alert classifications, you will:
1. Write a single-sentence insight for each stock that has an alert (daily or weekly)
2. Write a 1-2 sentence overall summary of what the watchlist shows today

Alert types:
- "consider_buy": RSI below 30 — strong oversold signal
- "watch": RSI between 30 and 35 — approaching oversold
- null: no alert, skip commentary

Respond ONLY with valid JSON matching this schema exactly:
{
  "tickers": [
    { "ticker": "AAPL", "commentary": "One sentence or null" }
  ],
  "summary": "Overall watchlist commentary"
}

Be factual and brief. Do not give financial advice.\
"""


def enrich(results: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    payload = json.dumps(
        [
            {
                "ticker": r["ticker"],
                "daily_rsi": r["daily_rsi"],
                "weekly_rsi": r["weekly_rsi"],
                "daily_alert": r["daily_alert"],
                "weekly_alert": r["weekly_alert"],
            }
            for r in results
        ],
        indent=2,
    )

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # cache prompt across daily runs
                }
            ],
            messages=[{"role": "user", "content": f"Analyze this watchlist:\n\n{payload}"}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if Claude wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        commentary_map = {t["ticker"]: t.get("commentary") for t in parsed.get("tickers", [])}
        enriched = [{**r, "commentary": commentary_map.get(r["ticker"])} for r in results]
        return enriched, parsed.get("summary", "")

    except Exception as e:
        print(f"[WARN] Claude enrichment failed ({e}) — sending report without commentary.")
        return [{**r, "commentary": None} for r in results], ""

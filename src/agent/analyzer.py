import json
import anthropic
from typing import List, Dict, Any, Tuple
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a concise stock technical analysis assistant focused on RSI signals and RSI divergence.

Given a watchlist of stocks with their RSI values, alert classifications, and divergence signals, you will:
1. Write a single-sentence insight for each stock that has any alert or divergence signal
2. Write a 1-2 sentence overall summary of what the watchlist shows today

RSI alert types:
- "strong_buy":    RSI below 25 — extremely oversold, strong buy signal
- "consider_buy":  RSI 25–30 — oversold, potential buy
- "watch":         RSI 30–35 — approaching oversold, watch for buy
- "warn":          RSI 65–70 — approaching overbought, watch for sell
- "consider_sell": RSI 70–75 — overbought, potential sell
- "strong_sell":   RSI above 75 — extremely overbought, strong sell signal
- null: no RSI alert

RSI Divergence types:
- "bullish": price made a lower low but RSI made a higher low — weakening downside momentum
- "bearish": price made a higher high but RSI made a lower high — weakening upside momentum
- null: no RSI divergence detected

A stock with no alerts AND no RSI divergence needs no commentary.

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
                "daily_rsi_divergence": r["daily_rsi_divergence"],
                "weekly_rsi_divergence": r["weekly_rsi_divergence"],
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

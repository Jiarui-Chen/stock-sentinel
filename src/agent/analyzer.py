import json
import anthropic
from typing import List, Dict, Any, Tuple
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.i18n import prompt_language_directive
from src import degradation

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a concise stock technical analysis assistant focused on RSI signals and RSI divergence.

You are writing for a long-term investor with a 6-18 month holding horizon, not a trader.
Treat RSI and divergence as entry/exit *timing* context for positions that will be held for
quarters, never as short-term trade signals. Weekly readings therefore matter more than daily
ones: a weekly extreme is a meaningful positioning cue, while a daily extreme is usually noise
that resolves long before the thesis plays out. Never suggest acting on a single day's reading.

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
Be factual and brief. Frame each insight in terms of what it means for a multi-quarter position
(e.g. a better/worse place to add or reduce), not what the stock might do this week.
Do not give financial advice.\
"""

_TOOL = {
    "name": "report_rsi_analysis",
    "description": "Report RSI analysis results for the watchlist",
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker":      {"type": "string"},
                        "commentary":  {"type": ["string", "null"]},
                    },
                    "required": ["ticker"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["tickers", "summary"],
    },
}


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
            max_tokens=1024,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_rsi_analysis"},
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT + prompt_language_directive(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": f"Analyze this watchlist:\n\n{payload}"}],
        )

        parsed = next(b for b in response.content if b.type == "tool_use").input
        commentary_map = {t["ticker"]: t.get("commentary") for t in parsed.get("tickers", [])}
        enriched = [{**r, "commentary": commentary_map.get(r["ticker"])} for r in results]
        return enriched, parsed.get("summary", "")

    except Exception as e:
        print(f"[WARN] Claude enrichment failed ({e}) — sending report without commentary.")
        degradation.record("commentary", e)
        return [{**r, "commentary": None} for r in results], ""

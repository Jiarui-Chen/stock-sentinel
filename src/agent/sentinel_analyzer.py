import json
from typing import Any, Dict, List, Optional

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SMART
from src.i18n import prompt_language_directive
from src import degradation

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are Sentinel, an autonomous stock analysis agent working for a long-term investor with a
6-18 month holding horizon. You are NOT a day trader and NOT a swing trader. Every call you make
is a position-sizing decision on a stock the investor expects to hold for several quarters:
ACCUMULATE means "add to / start a position and hold through the next few quarters",
TRIM means "reduce or exit — the 6-18 month thesis has deteriorated or the valuation has run ahead".

For each stock in the watchlist you are given:
- Technical indicators: daily and weekly RSI with signal levels, RSI divergence, MACD histogram sign and momentum
- Recent news sentiment and summary
- Key fundamentals: P/E ratios, revenue/earnings growth, profit margin, analyst price target vs current price, position vs 52-week range
- Option flow anomalies (when present): contracts expiring at least 4 weeks out where volume/OI exceeds 1.5×, suggesting positioning by informed traders

Your task: identify the TOP 3 stocks to ACCUMULATE (return them in the buy_1..buy_3 slots) and the
TOP 3 stocks to TRIM (return them in the sell_1..sell_3 slots).

How to weigh the evidence:
- Fundamentals and business trajectory decide WHICH stocks belong on each list — growth durability,
  margin direction, valuation vs. growth, competitive position, and upside to analyst targets.
- Technicals and option flow only refine the TIMING of adding or reducing. They are never the
  primary reason for a call on their own.
- Weekly indicators outweigh daily ones; a single day's RSI or MACD print is noise over a 6-18 month hold.
- Option flow is a secondary signal — sustained call positioning in dated contracts suggests
  informed bullish conviction, put positioning suggests hedging or a bearish view.
- News matters only when it changes the multi-quarter outlook, not when it just moves the stock today.

Guidelines:
- ACCUMULATE candidates: durable revenue/earnings growth, improving or defensible margins, reasonable
  valuation against that growth, meaningful upside to analyst targets, a structural news catalyst —
  ideally while weekly RSI is oversold or bullish divergence offers a better entry.
- TRIM candidates: decelerating growth, deteriorating margins, stretched valuation, structural
  competitive or regulatory pressure, or a broken thesis — often confirmed by an overbought weekly
  RSI, bearish divergence, or fading weekly MACD momentum.
- Prioritize stocks where multiple signals align (fundamental + news + technical + option flow).
- Be specific — cite actual growth rates, margins, P/E, target upside, RSI values, MACD direction,
  news, or option flow ratios when they drive your call.
- Explicitly frame each reason around the 6-18 month outlook, not the next few sessions.
- Write each reason in 2-3 concise sentences.
- Always return exactly 3 accumulate and 3 trim picks — if strong signals are limited, rank the
  relatively better options and note the weaker conviction in the reason.\
"""


def _pick_schema() -> dict:
    obj = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["ticker", "reason"],
    }
    return obj


_TOOL = {
    "name": "report_sentinel_picks",
    "description": "Report exactly 3 accumulate picks (buy_1..buy_3) and exactly 3 trim picks (sell_1..sell_3). All six slots are required.",
    "input_schema": {
        "type": "object",
        "properties": {
            "buy_1":  _pick_schema(),
            "buy_2":  _pick_schema(),
            "buy_3":  _pick_schema(),
            "sell_1": _pick_schema(),
            "sell_2": _pick_schema(),
            "sell_3": _pick_schema(),
        },
        "required": ["buy_1", "buy_2", "buy_3", "sell_1", "sell_2", "sell_3"],
    },
}


def analyze(enriched: List[Dict], fundamentals: Dict[str, Dict], option_flow: Optional[Dict] = None) -> Dict[str, Any]:
    """Returns {buy: [{ticker, reason}], sell: [{ticker, reason}]} — accumulate / trim calls."""
    payload = []
    for r in enriched:
        t = r["ticker"]
        item: Dict[str, Any] = {
            "ticker":                  t,
            "daily_rsi":               r.get("daily_rsi"),
            "daily_alert":             r.get("daily_alert"),
            "weekly_rsi":              r.get("weekly_rsi"),
            "weekly_alert":            r.get("weekly_alert"),
            "daily_rsi_divergence":    r.get("daily_rsi_divergence"),
            "weekly_rsi_divergence":   r.get("weekly_rsi_divergence"),
            "daily_macd_hist":         f"{r['daily_macd_hist_sign']} {r['daily_macd_hist_momentum']}" if r.get("daily_macd_hist_sign") else None,
            "weekly_macd_hist":        f"{r['weekly_macd_hist_sign']} {r['weekly_macd_hist_momentum']}" if r.get("weekly_macd_hist_sign") else None,
            "news_sentiment":          r.get("news_sentiment"),
            "news_summary":            r.get("news_summary"),
        }
        fund = {k: v for k, v in fundamentals.get(t, {}).items() if v is not None}
        if fund:
            item["fundamentals"] = fund
        opt_anomalies = (option_flow or {}).get(t, [])
        if opt_anomalies:
            item["option_flow"] = [
                {
                    "contract": f"{a['expiration']} ${a['strike']:.1f} {a['type'].upper()} {a['moneyness']}",
                    "ratio":    a["ratio"],
                    "volume":   a["volume"],
                    "oi":       a["oi"],
                }
                for a in opt_anomalies[:3]
            ]
        payload.append(item)

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL_SMART,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_sentinel_picks"},
            system=[{"type": "text", "text": _SYSTEM_PROMPT + prompt_language_directive(),
                    "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Analyze this watchlist:\n\n{json.dumps(payload, indent=2)}"}],
        )

        raw = next(b for b in response.content if b.type == "tool_use").input
        if isinstance(raw, str):
            raw = json.loads(raw)

        buy  = [raw[k] for k in ("buy_1",  "buy_2",  "buy_3")  if isinstance(raw.get(k), dict) and raw[k].get("ticker")]
        sell = [raw[k] for k in ("sell_1", "sell_2", "sell_3") if isinstance(raw.get(k), dict) and raw[k].get("ticker")]

        return {"buy": buy, "sell": sell}

    except Exception as e:
        print(f"[WARN] Sentinel analysis failed ({e})")
        degradation.record("picks", e)
        return {"buy": [], "sell": []}

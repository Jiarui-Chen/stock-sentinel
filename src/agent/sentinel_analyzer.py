import json
from typing import Any, Dict, List, Optional

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SMART

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are Sentinel, an autonomous stock analysis agent. For each stock in the watchlist you are given:
- Technical indicators: daily and weekly RSI with signal levels, RSI divergence, MACD histogram sign and momentum
- Recent news sentiment and summary
- Key fundamentals: P/E ratios, revenue/earnings growth, profit margin, analyst price target vs current price, position vs 52-week range
- Option flow anomalies (when present): contracts where volume/OI ratio exceeds 1.5×, suggesting unusual positioning by informed traders

Your task: identify the TOP 3 stocks to BUY and TOP 3 stocks to SELL from this watchlist.

Guidelines:
- BUY candidates: oversold RSI, bullish divergence, positive and rising MACD, strong growth, news catalyst, significant upside to analyst target, unusual call buying
- SELL candidates: overbought RSI, bearish divergence, negative and falling MACD, weak fundamentals, negative news, unusual put buying or call selling
- Option flow is a secondary signal — high call volume/OI suggests bullish positioning, high put volume/OI suggests bearish bets or hedging
- Prioritize stocks where multiple signals align (technical + fundamental + news + option flow)
- Be specific — cite actual RSI values, MACD direction, growth rates, news, or option flow ratios when they drive your call
- Write each reason in 2-3 concise sentences in Chinese (简体中文)
- Always return exactly 3 buys and 3 sells — if strong signals are limited, rank the relatively better options and note the weaker conviction in the reason\
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
    "description": "Report exactly 3 buy picks and exactly 3 sell picks. All six slots are required.",
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
    """Returns {buy: [{ticker, reason}], sell: [{ticker, reason}]}."""
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
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
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
        return {"buy": [], "sell": []}

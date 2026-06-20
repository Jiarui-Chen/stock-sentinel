import json
from typing import Any, Dict, List

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SMART

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are Sentinel, an autonomous stock analysis agent. For each stock in the watchlist you are given:
- Technical indicators: daily and weekly RSI with signal levels, RSI divergence, MACD histogram sign and momentum
- Recent news sentiment and summary
- Key fundamentals: P/E ratios, revenue/earnings growth, profit margin, analyst price target vs current price, position vs 52-week range

Your task: identify the TOP 3 stocks to BUY and TOP 3 stocks to SELL from this watchlist.

Guidelines:
- BUY candidates: oversold RSI, bullish divergence, positive and rising MACD, strong growth, news catalyst, significant upside to analyst target
- SELL candidates: overbought RSI, bearish divergence, negative and falling MACD, weak fundamentals, negative news, limited upside or downside risk
- Prioritize stocks where multiple signals align (technical + fundamental + news)
- Be specific — cite actual RSI values, MACD direction, growth rates, or news when they drive your call
- Write each reason in 2-3 concise sentences in Chinese (简体中文)
- If fewer than 3 clear buy or sell opportunities exist, return fewer — do not force weak picks\
"""

_TOOL = {
    "name": "report_analyst_picks",
    "description": "Report top 3 buy and top 3 sell picks from the watchlist with reasons.",
    "input_schema": {
        "type": "object",
        "properties": {
            "buy": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["ticker", "reason"],
                },
            },
            "sell": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["ticker", "reason"],
                },
            },
        },
        "required": ["buy", "sell"],
    },
}


def analyze(enriched: List[Dict], fundamentals: Dict[str, Dict]) -> Dict[str, Any]:
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
        payload.append(item)

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL_SMART,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_analyst_picks"},
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Analyze this watchlist:\n\n{json.dumps(payload, indent=2)}"}],
        )

        raw = next(b for b in response.content if b.type == "tool_use").input
        if isinstance(raw, str):
            raw = json.loads(raw)

        buy  = raw.get("buy",  [])
        sell = raw.get("sell", [])
        if isinstance(buy,  str): buy  = json.loads(buy)
        if isinstance(sell, str): sell = json.loads(sell)

        return {"buy": buy, "sell": sell}

    except Exception as e:
        print(f"[WARN] Sentinel analysis failed ({e})")
        return {"buy": [], "sell": []}

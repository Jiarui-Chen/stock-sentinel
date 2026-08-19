"""
Picks the option flows worth a long-term investor's attention across the whole watchlist.

src/indicators/option_flow.py flags every contract whose volume/OI ratio is abnormal
(already restricted to expirations at least 4 weeks out). That is typically dozens of
contracts — far too many for an email. This module hands the candidates to Claude and
asks for the TOP_N most meaningful flows, summarized in Chinese and grouped one bullet
per ticker.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SMART
from src.i18n import prompt_language_directive, brief_length_hint

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

TOP_N            = 5   # flows Claude may report across the entire watchlist
_PER_TICKER_KEEP = 4   # top candidates per ticker per ranking dimension (ratio, premium)
_MAX_CANDIDATES  = 60  # hard cap on what we send, to bound prompt size

_SYSTEM_PROMPT_TEMPLATE = """\
You are an options flow analyst serving a long-term investor with a 6-18 month holding horizon.

You are given unusual option activity across the investor's watchlist. Every candidate has already
been filtered to contracts expiring at least 4 weeks out, because near-dated speculation is
irrelevant to a multi-quarter thesis.

Your task: pick the {top_n} MOST MEANINGFUL flows across the ENTIRE watchlist and explain them.
That is {top_n} flows in TOTAL, not {top_n} per ticker. You are being deliberately selective: most of
the candidates you are given are not worth reporting, and you must leave them out. A "flow" is one
contract, or a tight cluster of near-identical contracts in the same name (same direction, adjacent
strikes or expirations) that clearly represents one position.

What makes a flow meaningful to this investor:
- Size that implies conviction — large estimated premium, not just a high ratio on a thin contract
- Longer-dated expirations (several months out, or LEAPS) over the shortest qualifying ones
- Strikes that imply a real directional view on the business, not lottery-ticket far-OTM prints
- Flow that corroborates or contradicts something structural about the company
- Repeated/clustered activity in one name across strikes or expirations — more telling than one print

Deprioritize: tiny contracts, single prints with negligible premium, and anything that reads as
routine hedging noise.

How to report:
- Return at most {top_n} bullets, ONE BULLET PER TICKER. If two of your chosen flows belong to the
  same ticker, merge them into that ticker's single bullet — so the bullet count may be fewer than
  {top_n}, but the flows described must never exceed {top_n} in total.
- Order bullets by how much the investor should care, most important first.
- Each summary: 1-2 sentences, {brief}. This is an email bullet, not a research note — say what
  was traded, what positioning it plausibly implies, and why a 6-18 month holder should care.
  Nothing else.
- Never list more than two contracts in one bullet. If a name has many prints, describe the pattern
  in aggregate instead of enumerating them.
- Be specific with numbers, but cite only the ones that carry the point — usually the expiration,
  strike, call/put, and either the volume/OI ratio or the rough premium, not every field.
- If nothing in the data is genuinely worth the investor's attention, return fewer bullets, or none.

Important caveats you must respect:
- Open interest is settled at the PRIOR day's close, so volume/OI ratios are approximate.
- Premium is estimated from a single last-traded print — treat it as an order of magnitude only.
- The data does NOT say whether a contract was bought or sold, and does not identify the trader.
  Say "positioning consistent with…" rather than asserting someone is bullish or bearish.
- Never state or imply this is a recommendation to trade options.\
"""

_TOOL = {
    "name": "report_option_flow",
    "description": (
        f"Report at most {TOP_N} notable option flows across the watchlist, grouped one bullet "
        "per ticker. Return an empty list if nothing is worth reporting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "bullets": {
                "type": "array",
                "maxItems": TOP_N,
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker":    {"type": "string"},
                        "sentiment": {"type": "string", "enum": ["bullish", "bearish", "mixed"]},
                        "contracts": {
                            "type": "string",
                            "description": "Short label for the contract(s), e.g. 'Jan 16 $250 CALL' or '3月/6月 $180 CALL'",
                        },
                        "summary": {
                            "type": "string",
                            "description": "1-2 sentences of prose",
                        },
                    },
                    "required": ["ticker", "sentiment", "contracts", "summary"],
                },
            },
        },
        "required": ["bullets"],
    },
}


def _system_prompt() -> str:
    """Prompt with the language-dependent bits resolved at call time."""
    return (
        _SYSTEM_PROMPT_TEMPLATE.format(top_n=TOP_N, brief=brief_length_hint())
        + prompt_language_directive()
    )


def _candidates(findings: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """
    Flatten findings into a bounded candidate pool.

    Ranking by ratio alone favours thin, illiquid contracts; ranking by premium alone
    hides genuinely anomalous small names. Take the top few on each dimension per ticker
    and union them, so Claude sees both kinds of signal.
    """
    pool: List[Dict[str, Any]] = []
    for rows in findings.values():
        by_ratio   = sorted(rows, key=lambda r: r["ratio"],          reverse=True)[:_PER_TICKER_KEEP]
        by_premium = sorted(rows, key=lambda r: r.get("premium") or 0, reverse=True)[:_PER_TICKER_KEEP]
        seen: set = set()
        for r in by_ratio + by_premium:
            key = (r["ticker"], r["expiration"], r["strike"], r["type"])
            if key in seen:
                continue
            seen.add(key)
            pool.append({
                "ticker":            r["ticker"],
                "expiration":        r["expiration"],
                "days_to_expiry":    r["days_to_exp"],
                "term":              r["term"],
                "type":              r["type"],
                "strike":            r["strike"],
                "moneyness":         r["moneyness"],
                "volume":            r["volume"],
                "open_interest":     r["oi"],
                "volume_oi_ratio":   r["ratio"],
                "est_premium_usd":   r.get("premium"),
                "implied_vol":       r.get("iv"),
            })

    # Bound the prompt: keep the largest-premium candidates when the pool is oversized.
    pool.sort(key=lambda c: c.get("est_premium_usd") or 0, reverse=True)
    return pool[:_MAX_CANDIDATES]


def analyze(findings: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """
    Returns [{ticker, sentiment, contracts, summary}] — at most TOP_N bullets,
    one per ticker, ordered most-notable first. Empty list if nothing to report.
    """
    if not findings:
        return []

    pool = _candidates(findings)
    if not pool:
        return []

    payload = json.dumps(pool, indent=2)
    today   = datetime.now().strftime("%Y-%m-%d")

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL_SMART,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_option_flow"},
            system=[{"type": "text", "text": _system_prompt(),
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": (
                    f"Today is {today}. Unusual option activity across the watchlist "
                    f"({len(pool)} candidate contracts):\n\n{payload}"
                ),
            }],
        )

        raw = next(b for b in response.content if b.type == "tool_use").input
        if isinstance(raw, str):
            raw = json.loads(raw)

        bullets = raw.get("bullets") if isinstance(raw, dict) else None
        if not isinstance(bullets, list):
            return []

        # Enforce one bullet per ticker and the TOP_N cap in code — the schema's
        # maxItems is a hint to the model, not a guarantee.
        out, seen = [], set()
        for b in bullets:
            if not isinstance(b, dict):
                continue
            ticker = str(b.get("ticker") or "").strip().upper()
            summary = str(b.get("summary") or "").strip()
            if not ticker or not summary or ticker in seen:
                continue
            seen.add(ticker)
            out.append({
                "ticker":    ticker,
                "sentiment": b.get("sentiment"),
                "contracts": str(b.get("contracts") or "").strip(),
                "summary":   summary,
            })
            if len(out) >= TOP_N:
                break
        return out

    except Exception as e:
        print(f"[WARN] Option flow analysis failed: {e}")
        return []

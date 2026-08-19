# Stock Sentinel

An autonomous AI agent that monitors your stock watchlist and delivers analysis to your inbox — no manual triggers required.

Every prompt in the system is written for a **long-term investor with a 6–18 month holding horizon**. Fundamentals and business trajectory decide *which* stocks matter; technicals and option flow only refine the *timing* of adding or reducing. Nothing here is tuned for day trading, and the agent is instructed not to reason that way.

## What it sends

| Email | When | Contents |
|---|---|---|
| **Daily report** | Once a day at `REPORT_TIME` | Accumulate/trim picks, upcoming earnings, top news, technical scorecard, option flow |
| **Earnings brief** | Evening of a ticker's earnings day, with a next-morning retry | Financial highlights, management takeaways, 6–18 month outlook, and answers to the watch points raised beforehand |
| **Pre-earnings preview** | 1–3 days before a ticker reports | Five things to watch this quarter, plus that stock's historical pre/post-earnings price pattern |

All three follow the language set by `REPORT_LANGUAGE`.

## The daily report

Sections appear in this order:

**1. Sentinel Picks** — Claude Sonnet reads the whole watchlist and names **3 stocks to accumulate (加仓 ▲)** and **3 to trim (减仓 ▼)**, each with a 2–3 sentence rationale. These are position-sizing calls on a multi-quarter hold, not trade signals: *accumulate* means start or add to a position, *trim* means the 6–18 month thesis has weakened or valuation has run ahead.

**2. Upcoming Earnings** — Any watchlist ticker reporting within 14 days, with a countdown and before/after-market timing.

**3. Top News** — The five most important stories across the watchlist, ranked by how much they change a company's 6–18 month trajectory. Guidance changes, structural demand shifts, and regulatory action score high; analyst price-target tweaks and daily price commentary score low.

**4. Scorecard** — One row per ticker, one colored dot per signal:

| Column | Meaning |
|---|---|
| RSI (D/W) | Oversold / neutral / overbought |
| Divergence (D/W) | Price and RSI moving in opposite directions |
| MACD Zero | Weekly trend bias — MACD line above or below zero |
| MACD Cross | Weekly timing trigger — bullish or bearish crossover |
| MACD Hist | Weekly momentum building or fading |
| Fwd PE | Forward price/earnings ratio |

🟢 bullish/oversold · 🟠 neutral/mixed · 🔴 bearish/overbought · ⚪ no signal

Rows sort by signal strength — extreme RSI first, then divergences, then MACD crossovers. Weekly readings are weighted more heavily than daily ones throughout, since a single day's print is noise over a multi-quarter hold.

**5. Option Flow** — The five most notable option flows across the *entire* watchlist, grouped one bullet per ticker. Claude picks them from every contract flagged as anomalous, weighing traded premium, days to expiry, and strike placement rather than just the raw ratio. **Only contracts expiring at least 4 weeks out are considered** — weekly options say nothing about a 6–18 month thesis.

## Signal reference

**RSI thresholds** (Wilder's smoothing, 14-period)

| Oversold | Signal | | Overbought | Signal |
|---|---|---|---|---|
| Below 25 | Strong Buy | | 65–70 | Warn |
| 25–30 | Consider Buy | | 70–75 | Consider Sell |
| 30–35 | Watch | | Above 75 | Strong Sell |

**RSI divergence** — detected independently on daily and weekly:
- *Bullish* — price made a lower low but RSI made a higher low (downside momentum weakening)
- *Bearish* — price made a higher high but RSI made a lower high (upside momentum weakening)

**Option flow anomalies** flag contracts where `volume / prior-day OI` exceeds a threshold. All thresholds live as constants at the top of [`src/indicators/option_flow.py`](src/indicators/option_flow.py):

| Constant | Default | Purpose |
|---|---|---|
| `RATIO_THRESHOLD` | 1.5 | Volume/OI ratio required to flag |
| `MIN_OI` | 20 | Skip thin contracts that produce spurious ratios |
| `MIN_VOLUME` | 50 | Skip trickle trades |
| `MIN_DAYS_TO_EXP` | 28 | Ignore anything expiring sooner |
| `MAX_EXPIRATIONS` | 6 | Qualifying expiry dates scanned per ticker |

> Open interest from yfinance is settled at the *prior* day's close, so ratios are approximate. Premium is estimated from a single last-traded print — treat it as an order of magnitude. The data never reveals whether a contract was bought or sold, so directional reads are inferred, not confirmed.

## Language

`REPORT_LANGUAGE` controls **every** string in **every** email — section headers, table labels, date formats, subject lines, and the language Claude writes its analysis in. Accepts `zh` (简体中文, the default) or `en`; anything else falls back to `zh` with a warning.

No mixing: an `en` report contains no Chinese, and a `zh` report contains no English prose. The only exceptions are ticker symbols, company names, and standard finance abbreviations — RSI, MACD, EPS, QoQ, YoY, P/E, CALL, PUT, ITM, ATM, OTM, LEAPS — which stay in English in both modes.

All translatable strings live in one table in [`src/i18n.py`](src/i18n.py). Adding a language means adding a column there and a date formatter; the reporters never branch on language themselves.

## Project structure

```
stock-sentinel/
├── main.py                          # Entry point, scheduler, CLI flags
├── watchlist.json                   # Tickers to monitor — edit freely
├── requirements.txt
├── .env.example                     # Environment variable template
├── com.stocksentinel.plist          # macOS launchd service config
├── tests/
│   └── test_fd_leak.py              # Regression guard for the fd leak
└── src/
    ├── config.py                    # All settings and env vars
    ├── i18n.py                      # Every user-visible string, both languages
    ├── data/
    │   ├── fetcher.py               # Daily/weekly OHLCV via yfinance
    │   ├── yf_session.py            # Shared HTTP session (prevents fd leaks)
    │   ├── news_fetcher.py          # 48h news headlines
    │   ├── fundamentals_fetcher.py  # P/E, growth, margin, analyst targets, earnings dates
    │   ├── earnings_fetcher.py      # SEC EDGAR 8-K filings + quarterly financials
    │   └── pre_earnings_fetcher.py  # Historical pre/post-earnings returns + sent-state
    ├── indicators/
    │   ├── rsi.py                   # RSI calculation and classification
    │   ├── rsi_divergence.py        # Swing-point divergence detection
    │   ├── macd.py                  # MACD line, signal, histogram
    │   └── option_flow.py           # Abnormal volume/OI scanner (4+ weeks out only)
    ├── agent/
    │   ├── analyzer.py              # Haiku — per-ticker RSI commentary
    │   ├── news_analyzer.py         # Haiku — news summary + importance scoring
    │   ├── pre_earnings_analyzer.py # Haiku — 5 watch points (with web search)
    │   ├── sentinel_analyzer.py     # Sonnet — accumulate/trim picks
    │   ├── earnings_analyzer.py     # Sonnet — earnings call interpretation
    │   └── option_flow_analyzer.py  # Sonnet — top 5 flows across the watchlist
    └── report/
        ├── email_reporter.py        # Daily HTML report + SMTP
        ├── earnings_reporter.py     # Earnings brief
        └── pre_earnings_reporter.py # Pre-earnings preview
```

## Setup

**1. Clone and create a virtual environment**
```bash
git clone <repo-url>
cd stock-sentinel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Configure environment variables**
```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
EMAIL_RECIPIENT=recipient@gmail.com
REPORT_TIME=18:00
REPORT_LANGUAGE=zh
```

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required |
| `EMAIL_SENDER` | — | Gmail address the reports are sent from |
| `EMAIL_PASSWORD` | — | Gmail **app password**, not your account password |
| `EMAIL_RECIPIENT` | — | One address, or several comma-separated |
| `REPORT_TIME` | `18:00` | Daily report time, 24-hour local |
| `REPORT_LANGUAGE` | `zh` | `zh` or `en` |
| `EARNINGS_EVENING_TIME` | `20:30` | Earnings-day check |
| `EARNINGS_MORNING_TIME` | `08:00` | Next-morning retry when metrics weren't published yet |

Multiple recipients:
```
EMAIL_RECIPIENT=alice@gmail.com,bob@gmail.com
```

> **Gmail App Password:** regular Gmail passwords won't work. Generate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requires 2-Step Verification).

**3. Edit your watchlist**

Open `watchlist.json` and add or remove tickers at any time:
```json
{
  "tickers": ["NVDA", "AAPL", "MSFT"]
}
```
The running service picks up changes on the next run — no restart needed.

## Running

```bash
source .venv/bin/activate

python3 main.py                           # Run on schedule (stays running)
python3 main.py --now                     # Daily report immediately, then exit
python3 main.py --earnings-now            # Earnings check for any ticker due today
python3 main.py --earnings-now AMZN       # Force an earnings brief for specific tickers
python3 main.py --pre-earnings-now AMZN   # Force a pre-earnings preview
```

Scan option flow standalone, without sending anything:
```bash
python3 -m src.indicators.option_flow TSLA NVDA AAPL
```

Run the regression tests:
```bash
python3 tests/test_fd_leak.py
```

On startup the scheduler waits up to 120 seconds for network reachability before its first run, and raises its open-file limit to the hard ceiling as defense against fd exhaustion.

## Deploy as a background service (macOS)

`com.stocksentinel.plist` points at a production checkout. **Edit the paths in it to match your machine** before installing — it ships with absolute paths that won't exist on your system.

```bash
cp com.stocksentinel.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.stocksentinel.plist
launchctl list | grep stocksentinel      # verify
```

**Managing the service**
```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.stocksentinel.plist

# Restart (needed after editing the plist or changing REPORT_TIME)
launchctl unload ~/Library/LaunchAgents/com.stocksentinel.plist
launchctl load ~/Library/LaunchAgents/com.stocksentinel.plist

# Logs (paths are set by StandardOutPath / StandardErrorPath in the plist)
tail -f <prod-dir>/logs/sentinel.log
tail -f <prod-dir>/logs/sentinel.error.log
```

Deploy updates with `git pull` inside the production directory. A launchd restart is only needed if the plist itself changed.

## Models and cost

| Agent | Model | Calls per daily run |
|---|---|---|
| RSI commentary | Haiku 4.5 | 1 |
| News summarization | Haiku 4.5 | 1 per ticker with news |
| Accumulate/trim picks | Sonnet 4.6 | 1 |
| Option flow summary | Sonnet 4.6 | 1 |
| Earnings analysis | Sonnet 4.6 | only on earnings days |
| Pre-earnings watch points | Haiku 4.5 | only 1–3 days before earnings |

Measured on an 18-ticker watchlist, running every day:

| Period | Estimated cost |
|---|---|
| Per daily run | ~$0.12 |
| Per month | ~$4.40 |
| Per year | ~$53 |

News summarization is roughly 40% of that, because `_BATCH_SIZE = 1` in [`src/agent/news_analyzer.py`](src/agent/news_analyzer.py) sends one API call per ticker and re-sends the system prompt each time. Raising the batch size is the single biggest cost lever. Everything else — yfinance, SEC EDGAR, Gmail SMTP, launchd — is free.

---

> Not financial advice.

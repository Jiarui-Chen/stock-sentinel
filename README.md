# Stock Sentinel

An autonomous AI agent that monitors your stock watchlist and delivers analysis to your inbox — no manual triggers required. It sends three kinds of reports:

1. **Daily watchlist report** — technicals, news, fundamentals, and option flow, with Claude-picked top buys and sells
2. **Earnings call reports** — fires the night a watchlist company reports, summarizing the results and management commentary
3. **Pre-earnings behavior reports** — fires in the days before a company reports, showing how the stock has historically moved around earnings plus AI-generated watch points

## What it does

### Daily watchlist report

- Reads a user-maintained watchlist (`watchlist.json`)
- Computes **daily and weekly RSI** for each ticker using Wilder's smoothing
- Detects **RSI divergence** (bullish and bearish) on both timeframes
- Computes **MACD histogram** (daily and weekly) — sign and momentum direction
- Renders an **inline MACD chart** per timeframe showing histogram bars, MACD line, and signal line
- Fetches **48h news headlines** via Yahoo Finance and summarizes relevant content in Chinese using Claude Haiku
- Fetches **key fundamentals** — P/E ratios, revenue/earnings growth, profit margin, analyst price target, 52-week range, and the next earnings date
- Scans **option flow anomalies** — flags contracts with unusually high volume/OI ratios, labeled by moneyness (ITM/ATM/OTM) and term (near/mid/LEAPS)
- Uses **Claude Sonnet** to pick the top 3 buys and top 3 sells from the watchlist, synthesizing technicals, fundamentals, news, and option flow
- Sends a formatted HTML email report every day at a configured time

### Earnings call reports

- When a watchlist company reports earnings (today or yesterday), fetches the earnings **transcript or press release from SEC EDGAR** (free, no API key) and **quarterly financials from yfinance**
- Uses **Claude Sonnet** to write a Chinese-language breakdown: financial highlights, management's key talking points, and a forward-looking interpretation — plus a review of the pre-earnings watch points if one was sent
- **Two-pass delivery** to handle data lag: a primary send the evening of the report, and a next-morning retry that fills in the financial metrics table if yfinance hadn't updated in time. Send-state is tracked in `logs/earnings_state.json` to prevent duplicates

### Pre-earnings behavior reports

- For any watchlist ticker whose earnings are **0–3 days out**, sends a one-time report before the call
- Shows how the stock moved in the **10 trading days before and after** each of its last 8 earnings calls (pre/post returns), with averages
- Uses **Claude Haiku with web search** to generate **5 watch points** for the upcoming call, drawing on the historical pattern, recent financials, news headlines, and live analyst-expectation searches
- The watch points are stored (`logs/pre_earnings_sent.json`) and later revisited in the earnings report so you can see how each played out

### Runs autonomously

- Runs as a background service via macOS launchd — starts on login, restarts on crash
- **Self-healing scheduler**: an error inside one scheduled job is caught and logged so it can never crash-loop the process or block other jobs
- Reuses a single pooled HTTP session for all market-data fetches and raises the open-file limit at startup, so the long-running process doesn't leak file descriptors over days of operation

## Signal levels

**RSI buy signals (oversold)**
| RSI | Signal |
|-----|--------|
| Below 25 | Strong Buy |
| 25–30 | Consider Buy |
| 30–35 | Watch |

**RSI sell signals (overbought)**
| RSI | Signal |
|-----|--------|
| 65–70 | Warn |
| 70–75 | Consider Sell |
| Above 75 | Strong Sell |

**RSI divergence** is detected independently on both timeframes:
- **Bullish divergence** — price made a lower low but RSI made a higher low (weakening downside momentum)
- **Bearish divergence** — price made a higher high but RSI made a lower high (weakening upside momentum)

**MACD histogram** reports the difference between the MACD line and signal line:
- Sign: positive or negative relative to zero
- Momentum: increasing or decreasing from the previous bar

**Option flow anomalies** flag contracts where `volume / prior-day OI` exceeds a threshold (default 1.5×), filtered by minimum OI (20) and minimum volume (50). Thresholds are adjustable constants in `src/indicators/option_flow.py`.

## Report formats

### Daily report

Each ticker gets its own card in the email, containing:

- **News** — 48h headlines summarized in Chinese with sentiment (shown only when relevant news exists)
- **Daily** — RSI with signal level, divergence if detected, and an inline MACD histogram chart (last 21 bars)
- **Weekly** — same as daily on the weekly timeframe
- **Options** — top 5 anomalous contracts sorted by ratio, showing expiry, strike, call/put, moneyness, ratio, and volume/OI

Tickers are sorted by signal strength — strongest RSI signals and divergences appear first.

At the top of the email, **Sentinel Picks** lists the top 3 buys (▲) and top 3 sells (▼) with reasons written in Chinese, selected by Claude Sonnet based on the full picture: technicals, fundamentals, news, and option flow.

The MACD chart is a PNG embedded directly in the email (CID attachment) and renders in Gmail, Apple Mail, and Outlook.

### Earnings report

Sent per company on the day it reports:

- **Financial highlights** with a metrics table — revenue, gross/operating margin, net income, EPS — each showing QoQ and YoY change (the table is omitted and retried the next morning if yfinance hasn't published the new quarter yet)
- **Management's key talking points** distilled from the EDGAR transcript / press release
- **Forward-looking interpretation** for the next 2–4 quarters
- **Watch-point review** — if a pre-earnings report was sent, each of its 5 watch points is answered against the actual results

### Pre-earnings report

Sent per company 0–3 days before it reports:

- A **historical pattern table** of pre- and post-earnings 10-trading-day returns for the last several quarters, with averages
- **5 watch points** for the upcoming call, generated by Claude Haiku with live web search

## Project structure

```
stock-sentinel/
├── main.py                          # Entry point, scheduler, and job wrappers
├── watchlist.json                   # Tickers to monitor — edit freely
├── requirements.txt
├── .env.example                     # Environment variable template
├── com.stocksentinel.plist          # macOS launchd service config
├── logs/                            # Runtime logs + send-state JSON
├── tests/
│   └── test_fd_leak.py              # Regression guard for the fd-leak fix
└── src/
    ├── config.py                    # All settings and env vars
    ├── data/
    │   ├── yf_session.py            # Shared, pooled yfinance HTTP session
    │   ├── fetcher.py               # Fetches OHLCV data via yfinance
    │   ├── news_fetcher.py          # Fetches 48h news headlines via yfinance
    │   ├── fundamentals_fetcher.py  # Fetches P/E, growth, margin, targets, earnings date
    │   ├── earnings_fetcher.py      # EDGAR transcript/press-release + yfinance financials
    │   └── pre_earnings_fetcher.py  # Historical pre/post-earnings return patterns
    ├── indicators/
    │   ├── rsi.py                   # RSI calculation and classification
    │   ├── rsi_divergence.py        # Swing point divergence detection
    │   ├── macd.py                  # MACD histogram + line series computation
    │   └── option_flow.py           # Abnormal volume/OI ratio scanner
    ├── agent/
    │   ├── analyzer.py              # Claude Haiku RSI enrichment
    │   ├── news_analyzer.py         # Claude Haiku news summarization (Chinese)
    │   ├── sentinel_analyzer.py     # Claude Sonnet top 3 buy/sell picks (Chinese)
    │   ├── pre_earnings_analyzer.py # Claude Haiku pre-earnings watch points + web search
    │   └── earnings_analyzer.py     # Claude Sonnet earnings call analysis (Chinese)
    └── report/
        ├── email_reporter.py        # Daily HTML email builder, PNG chart renderer, SMTP sender
        ├── earnings_reporter.py     # Earnings call analysis email
        └── pre_earnings_reporter.py # Pre-earnings pattern email
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

Edit `.env` with your credentials:
```
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
EMAIL_RECIPIENT=recipient@gmail.com

# Schedule times, 24-hour local time
REPORT_TIME=18:00              # daily watchlist report
EARNINGS_EVENING_TIME=20:30    # primary earnings send, same night
EARNINGS_MORNING_TIME=08:00    # earnings retry / metrics follow-up, next morning
```

All schedule times are optional and fall back to the defaults shown above.

Multiple recipients are supported — use a comma-separated list:
```
EMAIL_RECIPIENT=alice@gmail.com,bob@gmail.com
```

> **Gmail App Password:** regular Gmail passwords won't work. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) to generate one (requires 2-Step Verification to be enabled).

**3. Edit your watchlist**

Open `watchlist.json` and add or remove tickers at any time:
```json
{
  "tickers": ["NVDA", "AAPL", "MSFT"]
}
```
The running service picks up changes automatically on the next run — no restart needed.

## Running

**Daily report now (immediate, exits when done)**
```bash
source .venv/bin/activate
python3 main.py --now
```

**Earnings report now (test/manual)**
```bash
# Force specific tickers, bypassing date/state checks:
python3 main.py --earnings-now TSLA NVDA
# Or run the normal due-today logic against the watchlist:
python3 main.py --earnings-now
```

**Pre-earnings report now (test/manual)**
```bash
python3 main.py --pre-earnings-now AAPL MSFT
```

**Run on schedule (stays running)**
```bash
python3 main.py
```

**Test option flow scanner standalone**
```bash
python3 -m src.indicators.option_flow TSLA NVDA AAPL
```

**Run the fd-leak regression test**
```bash
python3 tests/test_fd_leak.py    # or: pytest tests/
```

## Deploy as a background service (macOS)

Register with launchd so the agent starts on login and restarts automatically if it crashes:

```bash
cp com.stocksentinel.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.stocksentinel.plist
```

Verify it's running:
```bash
launchctl list | grep stocksentinel
```

**Managing the service**
```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.stocksentinel.plist

# Restart (required after changing com.stocksentinel.plist or any schedule time in .env)
launchctl unload ~/Library/LaunchAgents/com.stocksentinel.plist
launchctl load ~/Library/LaunchAgents/com.stocksentinel.plist

# View logs
tail -f ~/Desktop/stock-sentinel-prod/logs/sentinel.log
tail -f ~/Desktop/stock-sentinel-prod/logs/sentinel.error.log
```

The plist raises the process's open-file limit above launchd's 256-fd default as a safety net, and `main.py` bumps its own soft limit to the hard ceiling at startup. Each scheduled run logs an `[fd] ...` line with its open-descriptor count — a steadily climbing number is the early-warning sign of a resource leak.

> **Note:** The service always runs from `~/Desktop/stock-sentinel-prod` (the production worktree on `main`). Deploy updates with `git pull` inside that directory. A launchd reload — and re-copying the plist to `~/Library/LaunchAgents/` — is needed whenever `com.stocksentinel.plist` or a schedule time changes.

## Scheduling behavior

The scheduler runs on wall-clock time every calendar day. If the Mac is **asleep** at a scheduled time, the job runs once as soon as it wakes; if the Mac is **powered off** (or sitting at the login screen, since this is a per-user LaunchAgent), that occurrence is skipped and the next run is at the following day's scheduled time — missed runs are not retroactively caught up. The earnings check is partly self-correcting because it looks at companies reporting **today or yesterday** and dedupes via its send-state file.

## Cost

Claude API usage per day depends on what's happening in your watchlist:

| Call | Model | When | Purpose |
|------|-------|------|---------|
| RSI enrichment | Haiku | Every daily run | Per-stock signal classification |
| News summarization | Haiku | Every daily run | 48h headline digest in Chinese |
| Sentinel picks | Sonnet | Every daily run | Top 3 buy/sell reasoning in Chinese |
| Pre-earnings watch points | Haiku + web search | Per ticker, 0–3 days before it reports | 5 watch points for the upcoming call |
| Earnings analysis | Sonnet | Per ticker, the day it reports | Financials + commentary breakdown |

The three daily calls are the baseline; pre-earnings and earnings calls occur only around each company's report date. Web search (used for pre-earnings watch points) is billed separately by Anthropic per search.

| Period | Estimated cost |
|--------|---------------|
| Per daily run | ~$0.05–0.10 |
| Per month | ~$2–4 (varies with earnings-season activity) |
| Per year | ~$20–40 |

All other components (yfinance, SEC EDGAR, Gmail SMTP, launchd) are free.

---

> Not financial advice.

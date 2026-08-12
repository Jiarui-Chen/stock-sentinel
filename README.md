# Stock Sentinel

An autonomous AI agent that monitors your stock watchlist daily and delivers a comprehensive analysis report to your inbox — no manual triggers required.

## What it does

- Reads a user-maintained watchlist (`watchlist.json`)
- Computes **daily and weekly RSI** for each ticker using Wilder's smoothing
- Detects **RSI divergence** (bullish and bearish) on both timeframes
- Computes **MACD histogram** (daily and weekly) — sign and momentum direction
- Renders an **inline MACD chart** per timeframe showing histogram bars, MACD line, and signal line
- Fetches **48h news headlines** via Yahoo Finance and summarizes relevant content in Chinese using Claude Haiku
- Fetches **key fundamentals** — P/E ratios, revenue/earnings growth, profit margin, analyst price target, 52-week range
- Scans **option flow anomalies** — flags contracts with unusually high volume/OI ratios, labeled by moneyness (ITM/ATM/OTM) and term (near/mid/LEAPS)
- Uses **Claude Sonnet** to pick the top 3 buys and top 3 sells from the watchlist, synthesizing technicals, fundamentals, news, and option flow
- Sends a formatted HTML email report every day at a configured time
- Runs autonomously as a background service via macOS launchd

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

## Report format

Each ticker gets its own card in the email, containing:

- **News** — 48h headlines summarized in Chinese with sentiment (shown only when relevant news exists)
- **Daily** — RSI with signal level, divergence if detected, and an inline MACD histogram chart (last 21 bars)
- **Weekly** — same as daily on the weekly timeframe
- **Options** — top 5 anomalous contracts sorted by ratio, showing expiry, strike, call/put, moneyness, ratio, and volume/OI

Tickers are sorted by signal strength — strongest RSI signals and divergences appear first.

At the top of the email, **Sentinel Picks** lists the top 3 buys (▲) and top 3 sells (▼) with reasons written in Chinese, selected by Claude Sonnet based on the full picture: technicals, fundamentals, news, and option flow.

The MACD chart is a PNG embedded directly in the email (CID attachment) and renders in Gmail, Apple Mail, and Outlook.

## Project structure

```
stock-sentinel/
├── main.py                        # Entry point and scheduler
├── watchlist.json                 # Tickers to monitor — edit freely
├── requirements.txt
├── .env.example                   # Environment variable template
├── com.stocksentinel.plist        # macOS launchd service config
└── src/
    ├── config.py                  # All settings and env vars
    ├── data/
    │   ├── fetcher.py             # Fetches OHLCV data via yfinance
    │   ├── news_fetcher.py        # Fetches 48h news headlines via yfinance
    │   └── fundamentals_fetcher.py  # Fetches P/E, growth, margin, analyst targets
    ├── indicators/
    │   ├── rsi.py                 # RSI calculation and classification
    │   ├── rsi_divergence.py      # Swing point divergence detection
    │   ├── macd.py                # MACD histogram + line series computation
    │   └── option_flow.py         # Abnormal volume/OI ratio scanner
    ├── agent/
    │   ├── news_analyzer.py       # Claude Haiku news summarization (Chinese)
    │   └── sentinel_analyzer.py   # Claude Sonnet top 3 buy/sell picks (Chinese)
    └── report/
        └── email_reporter.py      # HTML email builder, PNG chart renderer, SMTP sender
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
REPORT_TIME=16:30
```

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

**Test run (immediate, exits when done)**
```bash
source .venv/bin/activate
python3 main.py --now
```

**Run on schedule (stays running)**
```bash
python3 main.py
```

**Test option flow scanner standalone**
```bash
python3 -m src.indicators.option_flow TSLA NVDA AAPL
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

# Restart (required after changing com.stocksentinel.plist or REPORT_TIME in .env)
launchctl unload ~/Library/LaunchAgents/com.stocksentinel.plist
launchctl load ~/Library/LaunchAgents/com.stocksentinel.plist

# View logs
tail -f ~/Desktop/stock-sentinel-prod/logs/sentinel.log
tail -f ~/Desktop/stock-sentinel-prod/logs/sentinel.error.log
```

> **Note:** The service always runs from `~/Desktop/stock-sentinel-prod` (the production worktree on `main`). Deploy updates with `git pull` inside that directory. A launchd restart is only needed if `com.stocksentinel.plist` or `REPORT_TIME` changed.

## Cost

Two Claude API calls per daily run — Haiku for bulk tasks, Sonnet for Sentinel picks:

| Call | Model | Purpose |
|------|-------|---------|
| News summarization | Haiku | 48h headline digest in Chinese |
| Sentinel picks | Sonnet | Top 3 buy/sell reasoning in Chinese |

| Period | Estimated cost |
|--------|---------------|
| Per run | ~$0.05–0.10 |
| Per month | ~$1–2 |
| Per year | ~$15–25 |

All other components (yfinance, Gmail SMTP, launchd) are free.

---

> Not financial advice.

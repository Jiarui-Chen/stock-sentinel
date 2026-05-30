# Stock Sentinel

An autonomous AI agent that monitors your stock watchlist daily and delivers an RSI analysis report to your inbox — no manual triggers required.

## What it does

- Reads a user-maintained watchlist (`watchlist.json`)
- Computes **daily RSI** (short-term) and **weekly RSI** (long-term) for each ticker using Wilder's smoothing
- Detects **RSI divergence** (bullish and bearish) on both daily and weekly timeframes
- Classifies signals across 6 levels from strong buy to strong sell
- Uses **Claude Haiku** to generate per-stock insights and an overall market summary
- Fetches **24h news headlines** via Yahoo Finance and summarizes them in Chinese using Claude Haiku
- Sends a formatted HTML email report every weekday at a configured time
- Runs autonomously as a background service via macOS launchd

## Signal levels

**Buy signals (oversold)**
| RSI | Signal |
|-----|--------|
| Below 25 | Strong Buy |
| 25–30 | Consider Buy |
| 30–35 | Watch |

**Sell signals (overbought)**
| RSI | Signal |
|-----|--------|
| 65–70 | Warn |
| 70–75 | Consider Sell |
| Above 75 | Strong Sell |

RSI divergence is detected independently and surfaced alongside RSI signals:
- **Bullish divergence** — price made a lower low but RSI made a higher low
- **Bearish divergence** — price made a higher high but RSI made a lower high

## Report structure

1. **Claude summary** — 1–2 sentence overall market commentary
2. **News (24h)** — recent headlines per ticker with sentiment and investment implication in Chinese
3. **Long-term signals** (weekly RSI) — buy and sell sections
4. **Short-term signals** (daily RSI) — compact single table

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
    │   └── news_fetcher.py        # Fetches 24h news headlines via yfinance
    ├── indicators/
    │   ├── rsi.py                 # RSI calculation and classification
    │   └── rsi_divergence.py      # Swing point divergence detection
    ├── agent/
    │   ├── analyzer.py            # Claude Haiku RSI enrichment
    │   └── news_analyzer.py       # Claude Haiku news summarization (Chinese)
    └── report/
        └── email_reporter.py      # HTML email builder and SMTP sender
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
REPORT_TIME=18:00
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
python main.py --now
```

**Run on schedule (stays running)**
```bash
python main.py
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

Two Claude Haiku API calls per weekday run (RSI enrichment + news summarization):

| Period | Estimated cost |
|--------|---------------|
| Per run | ~$0.005 |
| Per month | ~$0.10 |
| Per year | ~$1.20 |

All other components (yfinance, Gmail SMTP, launchd) are free.

---

> Not financial advice.

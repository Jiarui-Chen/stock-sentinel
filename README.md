# Stock Sentinel

An autonomous AI agent that monitors your stock watchlist daily and delivers an RSI analysis report to your inbox — no manual triggers required.

## What it does

- Reads a user-maintained watchlist (`watchlist.json`)
- Computes **daily RSI** (short-term) and **weekly RSI** (long-term) for each ticker
- Flags stocks approaching oversold territory
- Uses **Claude Haiku** to generate a concise insight per flagged stock and an overall market summary
- Sends a formatted HTML email report every weekday at a configured time
- Runs autonomously as a background service via macOS launchd

## Alert thresholds

| RSI | Signal |
|-----|--------|
| Below 35 | Low RSI Watch |
| Below 30 | Low RSI Consider Buy |

Both daily and weekly RSI are evaluated independently, surfacing short-term and long-term signals in separate sections of the report.

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
    │   └── fetcher.py             # Fetches OHLCV data via yfinance
    ├── indicators/
    │   └── rsi.py                 # RSI calculation (Wilder's smoothing)
    ├── agent/
    │   └── analyzer.py            # Claude Haiku enrichment
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

**Test run (immediate)**
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

# Restart (e.g. after changing .env)
launchctl unload ~/Library/LaunchAgents/com.stocksentinel.plist
launchctl load ~/Library/LaunchAgents/com.stocksentinel.plist

# View logs
tail -f logs/sentinel.log
tail -f logs/sentinel.error.log
```

## Cost

The only paid component is the Claude Haiku API call (~1 per weekday):

| Period | Estimated cost |
|--------|---------------|
| Per run | ~$0.0015 |
| Per month | ~$0.03 |
| Per year | ~$0.40 |

All other components (yfinance, Gmail SMTP, launchd) are free.

---

> Not financial advice.

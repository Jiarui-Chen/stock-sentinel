import os
from dotenv import load_dotenv

load_dotenv()

# RSI thresholds — oversold / overbought
RSI_PERIOD = 14
RSI_STRONG_BUY_THRESHOLD  = 25   # oversold — strong buy
RSI_BUY_THRESHOLD         = 30   # oversold — consider buy
RSI_WATCH_THRESHOLD       = 35   # oversold — watch
RSI_WARN_THRESHOLD        = 65   # overbought — warn
RSI_SELL_THRESHOLD        = 70   # overbought — consider sell
RSI_STRONG_SELL_THRESHOLD = 75   # overbought — strong sell

# Email
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Scheduler — 24-hour format, runs on weekdays only
REPORT_TIME = os.getenv("REPORT_TIME", "18:00")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL        = "claude-haiku-4-5-20251001"   # bulk tasks: RSI enrichment, news summarization
CLAUDE_MODEL_SMART  = "claude-sonnet-4-6"           # reasoning tasks: Sentinel picks

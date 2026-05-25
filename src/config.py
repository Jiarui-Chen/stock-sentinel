import os
from dotenv import load_dotenv

load_dotenv()

# RSI
RSI_PERIOD = 14
RSI_WATCH_THRESHOLD = 35
RSI_BUY_THRESHOLD = 30

# Email
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Scheduler — 24-hour format, runs on weekdays only
REPORT_TIME = os.getenv("REPORT_TIME", "18:00")

# Claude — use Haiku for lowest cost
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

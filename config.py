import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")

MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
TEXT_TRIGGER_ENABLED = os.getenv("TEXT_TRIGGER_ENABLED", "false").lower() == "true"
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.4"))

# Proxy for Discord connections (your machine needs one to reach discord.com).
# Set PROXY= empty in .env to disable.
PROXY = os.getenv("PROXY", os.environ.get("HTTPS_PROXY", "")).strip() or None

TRIGGER = "/ask"

# GitHub releases -> Discord announcements
GITHUB_REPO = os.getenv("GITHUB_REPO", "embeddiumAI/Desktop")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip() or None
ANNOUNCEMENTS_CHANNEL_ID = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "0"))
CHANGELOG_CHANNEL_ID = int(os.getenv("CHANGELOG_CHANNEL_ID", "0"))
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))
ANNOUNCE_ROLE_ID = int(os.getenv("ANNOUNCE_ROLE_ID", "0"))  # 0 = no role mention
BIG_UPDATE_KEYWORDS = [k.strip().lower() for k in os.getenv("BIG_UPDATE_KEYWORDS", "BREAKING,major,security,migration").split(",") if k.strip()]

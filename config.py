"""
Token Data Collector - Configuration
"""
import os
from pathlib import Path

# ── Directories ──────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── API Keys ──────────────────────────────────────────────
# CoinMarketCap API key (required)
# Get one: https://pro.coinmarketcap.com/signup
CMC_API_KEY = os.getenv("CMC_API_KEY", "")

# CoinGecko is free, no API key needed
# Optional: CoinGecko Pro API key
CG_API_KEY = os.getenv("CG_API_KEY", "")

# ── Collection Settings ──────────────────────────────────
TOP_N = 300  # Number of coins to track
REQUEST_TIMEOUT = 30  # seconds

# CMC API
CMC_LISTINGS_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
CMC_QUOTES_URL = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"

# CoinGecko API
CG_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
CG_BASE_URL = "https://api.coingecko.com/api/v3"

# ── Validation Thresholds ────────────────────────────────
# Discrepancy percentage that triggers "conflict" badge
DISCREPANCY_THRESHOLD = 10  # percent

# CG ratio vs CMC ratio: if CG is this much lower, mark as stale
STALE_CG_THRESHOLD = 0.5  # CG ratio < CMC ratio * 0.5

# Maximum acceptable age for CG data (hours)
CG_MAX_AGE_HOURS = 6

# ── Cloudflare KV ────────────────────────────────────────
# KV namespace ID for the dashboard
KV_NAMESPACE_ID = "6d56b8307fd04814892f9c2b15723c02"
KV_DATA_KEY = "market_data"
KV_HTML_KEY = "dashboard_html"

# Cloudflare API (uses env vars or direct config)
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "1ab09277ed038add4925d28a343c9dc5")
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "")

# ── GitHub Actions ───────────────────────────────────────
# When running in GitHub Actions, these are set automatically
GITHUB_SHA = os.getenv("GITHUB_SHA", "local")
RUN_ID = os.getenv("GITHUB_RUN_ID", "local")

# ── Data File Paths ──────────────────────────────────────
CMC_SNAPSHOT = DATA_DIR / "cmc_latest.json"
CG_SNAPSHOT = DATA_DIR / "cg_latest.json"
MERGED_SNAPSHOT = DATA_DIR / "merged_latest.json"
QUALITY_REPORT = DATA_DIR / "quality_report.json"
HISTORY_DIR = DATA_DIR / "history"

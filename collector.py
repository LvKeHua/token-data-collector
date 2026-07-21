"""
Collector: Fetch raw market data from CoinMarketCap and CoinGecko APIs.
"""
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional
import requests

from config import (
    CMC_API_KEY, CG_API_KEY,
    CMC_LISTINGS_URL, CG_MARKETS_URL,
    CMC_SNAPSHOT, CG_SNAPSHOT, MERGED_SNAPSHOT,
    TOP_N, REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  CoinMarketCap
# ═══════════════════════════════════════════════════════════

def fetch_cmc() -> list[dict]:
    """Fetch top N coins from CMC."""
    if not CMC_API_KEY:
        logger.warning("CMC_API_KEY not set, skipping CMC fetch")
        return []

    headers = {
        "X-CMC_PRO_API_KEY": CMC_API_KEY,
        "Accept": "application/json",
    }
    params = {
        "start": 1,
        "limit": TOP_N,
        "convert": "USD",
        "sort": "market_cap",
        "sort_dir": "desc",
    }

    logger.info("Fetching CMC listings (top %d)...", TOP_N)
    resp = requests.get(
        CMC_LISTINGS_URL, headers=headers, params=params,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    coins = data.get("data", [])
    logger.info("CMC returned %d coins", len(coins))

    # Normalise
    normalised = []
    for c in coins:
        quote = c.get("quote", {}).get("USD", {})
        max_supply = c.get("max_supply")
        circ_supply = c.get("circulating_supply")
        circ_ratio = None
        if circ_supply and max_supply:
            circ_ratio = round(circ_supply / max_supply * 100, 2)

        normalised.append({
            "source": "cmc",
            "id": str(c["id"]),
            "symbol": c["symbol"],
            "name": c["name"],
            "slug": c.get("slug", ""),
            "price": quote.get("price"),
            "market_cap": quote.get("market_cap"),
            "volume_24h": quote.get("volume_24h"),
            "percent_change_1h": quote.get("percent_change_1h"),
            "percent_change_24h": quote.get("percent_change_24h"),
            "percent_change_7d": quote.get("percent_change_7d"),
            "circulating_supply": circ_supply,
            "max_supply": max_supply,
            "circulating_ratio": circ_ratio,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    # Save raw snapshot
    CMC_SNAPSHOT.write_text(json.dumps(normalised, indent=2, ensure_ascii=False))
    logger.info("CMC snapshot saved: %s", CMC_SNAPSHOT)
    return normalised


# ═══════════════════════════════════════════════════════════
#  CoinGecko
# ═══════════════════════════════════════════════════════════

def fetch_cg() -> list[dict]:
    """Fetch top coins from CoinGecko."""
    headers = {"Accept": "application/json"}
    if CG_API_KEY:
        headers["x-cg-pro-api-key"] = CG_API_KEY

    # CoinGecko paginates 250 per page, need 2 pages for top 300
    all_coins = []
    for page in range(1, 3):
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": page,
            "sparkline": "false",
        }
        logger.info("Fetching CG page %d ...", page)
        try:
            resp = requests.get(
                CG_MARKETS_URL, headers=headers, params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            page_data = resp.json()
            if not page_data:
                break
            all_coins.extend(page_data)
            time.sleep(1.5)  # rate limit
        except Exception as e:
            logger.warning("CG page %d failed: %s", page, e)
            break

    logger.info("CG returned %d coins total", len(all_coins))

    # Normalise
    normalised = []
    for c in all_coins:
        max_supply = c.get("max_supply")
        circ_supply = c.get("circulating_supply")
        total_supply = c.get("total_supply")
        circ_ratio = None
        if circ_supply and max_supply:
            circ_ratio = round(circ_supply / max_supply * 100, 2)

        normalised.append({
            "source": "coingecko",
            "id": c.get("id", ""),
            "symbol": c.get("symbol", "").upper(),
            "name": c.get("name", ""),
            "price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "volume_24h": c.get("total_volume"),
            "percent_change_1h": c.get("price_change_percentage_1h_in_currency"),
            "percent_change_24h": c.get("price_change_percentage_24h"),
            "percent_change_7d": c.get("price_change_percentage_7d"),
            "circulating_supply": circ_supply,
            "max_supply": max_supply,
            "total_supply": total_supply,
            "circulating_ratio": circ_ratio,
            "last_updated": c.get("last_updated", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    # Save raw snapshot
    CG_SNAPSHOT.write_text(json.dumps(normalised, indent=2, ensure_ascii=False))
    logger.info("CG snapshot saved: %s", CG_SNAPSHOT)
    return normalised


# ═══════════════════════════════════════════════════════════
#  Merge
# ═══════════════════════════════════════════════════════════

def merge(cmc_coins: list[dict], cg_coins: list[dict]) -> list[dict]:
    """
    Merge CMC and CG data by symbol.
    Each output coin has fields from both sources.
    """
    cg_by_symbol = {c["symbol"]: c for c in cg_coins if c.get("symbol")}

    merged = []
    for cmc in cmc_coins:
        sym = cmc["symbol"]
        cg = cg_by_symbol.pop(sym, None)  # remove to track unmatched later

        item = {
            "symbol": sym,
            "name": cmc.get("name") or (cg or {}).get("name", ""),
            "slug": cmc.get("slug", ""),

            # CMC fields
            "cmc_price": cmc.get("price"),
            "cmc_market_cap": cmc.get("market_cap"),
            "cmc_volume_24h": cmc.get("volume_24h"),
            "cmc_circulating_supply": cmc.get("circulating_supply"),
            "cmc_max_supply": cmc.get("max_supply"),
            "cmc_circulating_ratio": cmc.get("circulating_ratio"),
            "cmc_change_1h": cmc.get("percent_change_1h"),
            "cmc_change_24h": cmc.get("percent_change_24h"),
            "cmc_change_7d": cmc.get("percent_change_7d"),

            # CG fields
            "cg_id": (cg or {}).get("id", ""),
            "cg_price": (cg or {}).get("price"),
            "cg_market_cap": (cg or {}).get("market_cap"),
            "cg_volume_24h": (cg or {}).get("volume_24h"),
            "cg_circulating_supply": (cg or {}).get("circulating_supply"),
            "cg_max_supply": (cg or {}).get("max_supply"),
            "cg_total_supply": (cg or {}).get("total_supply"),
            "cg_circulating_ratio": (cg or {}).get("circulating_ratio"),
            "cg_change_1h": (cg or {}).get("percent_change_1h"),
            "cg_change_24h": (cg or {}).get("percent_change_24h"),
            "cg_change_7d": (cg or {}).get("percent_change_7d"),
            "cg_last_updated": (cg or {}).get("last_updated", ""),

            "has_cmc": True,
            "has_cg": cg is not None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        merged.append(item)

    # Remaining CG-only coins (those not matched by symbol in CMC)
    for sym, cg in cg_by_symbol.items():
        merged.append({
            "symbol": sym,
            "name": cg.get("name", ""),
            "slug": "",
            "cmc_price": None, "cmc_market_cap": None,
            "cmc_circulating_ratio": None,
            "cg_id": cg.get("id", ""),
            "cg_price": cg.get("price"),
            "cg_market_cap": cg.get("market_cap"),
            "cg_circulating_ratio": cg.get("circulating_ratio"),
            "has_cmc": False,
            "has_cg": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    merged.sort(key=lambda x: -(x.get("cmc_market_cap") or x.get("cg_market_cap") or 0))
    logger.info("Merged: %d coins (CMC+CGC), %d CG-only",
                len(merged) - len(cg_by_symbol), len(cg_by_symbol))

    # Save merged snapshot
    MERGED_SNAPSHOT.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    return merged


# ═══════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════

def collect() -> list[dict]:
    """Full collection pipeline: CMC → CG → merge."""
    logger.info("=" * 50)
    logger.info("Starting data collection run")
    logger.info("=" * 50)

    cmc = fetch_cmc()
    cg = fetch_cg()
    merged = merge(cmc, cg)

    logger.info("Collection complete: %d merged coins", len(merged))
    return merged


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    collect()

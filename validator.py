"""
Validator: Cross-validate CMC vs CoinGecko data, detect anomalies, compute quality metrics.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from config import (
    MERGED_SNAPSHOT, QUALITY_REPORT,
    DISCREPANCY_THRESHOLD, STALE_CG_THRESHOLD, CG_MAX_AGE_HOURS,
    HISTORY_DIR,
)

logger = logging.getLogger(__name__)


def validate(merged: list[dict]) -> list[dict]:
    """
    Validate each coin and add quality/flags.
    Returns enriched list with data_conflict, stale_cg_data, discrepancy_pct, etc.
    """
    enriched = []
    stats = {
        "total": len(merged),
        "with_both_sources": 0,
        "cmc_only": 0,
        "cg_only": 0,
        "with_conflict": 0,
        "stale_cg": 0,
        "no_ratio": 0,
        "conflict_breakdown": {},  # discrepancy ranges
    }

    for coin in merged:
        cmc_ratio = coin.get("cmc_circulating_ratio")
        cg_ratio = coin.get("cg_circulating_ratio")
        cg_updated = coin.get("cg_last_updated", "")

        # Determine source coverage
        has_cmc = coin.get("has_cmc", False)
        has_cg = coin.get("has_cg", False)
        if has_cmc and has_cg:
            stats["with_both_sources"] += 1
        elif has_cmc and not has_cg:
            stats["cmc_only"] += 1
        elif has_cg and not has_cmc:
            stats["cg_only"] += 1

        # Default flags
        data_conflict = False
        stale_cg_data = False
        discrepancy_pct = 0

        # Pick the best ratio
        if cmc_ratio is not None and cg_ratio is not None:
            # Both sources available → cross-validate
            diff = abs(cmc_ratio - cg_ratio)
            discrepancy_pct = round(diff, 2)

            if diff > DISCREPANCY_THRESHOLD:
                data_conflict = True
                stats["with_conflict"] += 1
                # Breakdown by severity
                bucket = f"{diff:.0f}%"
                stats["conflict_breakdown"][bucket] = stats["conflict_breakdown"].get(bucket, 0) + 1

            # Stale detection: CG ratio significantly lower than CMC
            if cg_ratio < cmc_ratio * STALE_CG_THRESHOLD:
                stale_cg_data = True
                stats["stale_cg"] += 1

            # Use CMC as the canonical ratio (more reliable)
            canonical_ratio = cmc_ratio
        elif cmc_ratio is not None:
            canonical_ratio = cmc_ratio
        else:
            canonical_ratio = cg_ratio

        if canonical_ratio is None:
            stats["no_ratio"] += 1

        # Build the enriched coin object (dashboard-compatible format)
        entry = {
            "symbol": coin["symbol"],
            "name": coin.get("name", ""),

            # Price: prefer CMC, fallback to CG
            "price": coin.get("cmc_price") or coin.get("cg_price"),

            # Market cap: prefer CMC
            "market_cap": coin.get("cmc_market_cap") or coin.get("cg_market_cap"),

            # Canonical circulating ratio
            "circulating_ratio": canonical_ratio,

            # CoinGecko ratio for dual display
            "cg_ratio": cg_ratio,

            # Volume: prefer CMC
            "volume_24h_usdt": coin.get("cmc_volume_24h") or coin.get("cg_volume_24h"),

            # Changes: prefer CMC
            "percent_change_24h": coin.get("cmc_change_24h") or coin.get("cg_change_24h"),
            "percent_change_7d": coin.get("cmc_change_7d") or coin.get("cg_change_7d"),
            "amplitude_24h_pct": None,  # computed from high/low if available

            # Quality flags
            "data_conflict": data_conflict,
            "stale_cg_data": stale_cg_data,
            "discrepancy_pct": discrepancy_pct,

            # Source tracking
            "data_sources": {
                "cmc": has_cmc,
                "coingecko": has_cg,
            },

            # Metadata
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        # Compute star rating based on data quality + fundamentals
        entry["star_rating"] = _compute_star_rating(entry)
        entry["momentum_alert"] = _check_momentum(entry)
        entry["unlock_risk"] = _compute_unlock_risk(entry)

        enriched.append(entry)

    # Sort by market cap descending
    enriched.sort(key=lambda x: -(x["market_cap"] or 0))

    # Build report
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_coins": stats["total"],
        "coins_with_cmc_and_cg": stats["with_both_sources"],
        "coins_with_conflict": stats["with_conflict"],
        "coins_stale_cg": stats["stale_cg"],
        "coins_no_ratio": stats["no_ratio"],
        "conflict_breakdown": stats["conflict_breakdown"],
        "quality_score": _compute_quality_score(stats),
    }
    logger.info("Validation report: %s", json.dumps(report, indent=2))

    # Save report
    QUALITY_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Archive to history
    HISTORY_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    (HISTORY_DIR / f"report_{ts}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )

    return enriched


def _compute_star_rating(coin: dict) -> int:
    """
    Compute star rating (0-5) based on fundamentals + data quality.
    Mirrors the logic in the Worker's assignStars().
    """
    score = 0
    cr = coin.get("circulating_ratio")

    # Low circulating ratio → more potential upside
    if cr is not None:
        if cr < 10:
            score += 3
        elif cr < 30:
            score += 2
        elif cr < 50:
            score += 1
        elif cr > 90:
            score -= 1  # fully diluted

    # Price momentum
    chg7d = coin.get("percent_change_7d")
    if chg7d is not None:
        if chg7d > 30:
            score += 2
        elif chg7d > 10:
            score += 1
        elif chg7d < -20:
            score -= 1

    # Data quality penalty
    if coin.get("data_conflict"):
        score -= 1

    return max(0, min(5, score))


def _check_momentum(coin: dict) -> bool:
    """Check if coin has strong momentum (7d > 30% AND 24h > 5%)."""
    chg7d = coin.get("percent_change_7d")
    chg24h = coin.get("percent_change_24h")
    return bool(chg7d and chg24h and chg7d > 30 and chg24h > 5)


def _compute_unlock_risk(coin: dict) -> str:
    """
    Estimate unlock risk based on circulating ratio.
    Low ratio = high future dilution risk.
    """
    cr = coin.get("circulating_ratio")
    if cr is None:
        return "未知"
    if cr < 15:
        return "🔴 高通胀风险"
    if cr < 30:
        return "🟡 中等通胀风险"
    return "🟢 低风险"


def _compute_quality_score(stats: dict) -> float:
    """
    Overall data quality score (0-100).
    Higher = better data trustworthiness.
    """
    total = stats["total"] or 1
    both = stats["with_both_sources"]
    conflicts = stats["with_conflict"]
    stale = stats["stale_cg"]
    no_ratio = stats["no_ratio"]

    # Base: percentage of coins with both sources
    score = (both / total) * 60

    # Penalty for conflicts
    score -= (conflicts / total) * 20

    # Penalty for stale data
    score -= (stale / total) * 15

    # Penalty for no ratio at all
    score -= (no_ratio / total) * 5

    return round(max(0, score), 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if MERGED_SNAPSHOT.exists():
        data = json.loads(MERGED_SNAPSHOT.read_text())
        result = validate(data)
        logger.info("Validated %d coins", len(result))
    else:
        logger.error("No merged snapshot found. Run collector.py first.")

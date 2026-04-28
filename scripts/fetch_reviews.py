"""
fetch_reviews.py — pulls reviews from Trustpilot, AskGamblers, CasinoGuru
for Lucky Dreams, RocketPlay, and OnlyWin casinos.

Usage:
    # Mock mode — no credentials, for testing/demo:
    REVIEWS_MOCK=true python scripts/fetch_reviews.py

    # Real mode:
    APIFY_API_TOKEN=your_token python scripts/fetch_reviews.py

Outputs JSON list of reviews to stdout. Exits 1 on any error.
"""
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Brand config — update slugs if URLs change
# ---------------------------------------------------------------------------

BRANDS = {
    "lucky_dreams": {
        "name": "Lucky Dreams Casino",
        "trustpilot_domain": "luckydreams.com",
        "askgamblers_slug": "lucky-dreams-casino",
        "casinoguru_slug": "lucky-dreams-casino-review",
    },
    "rocket_play": {
        "name": "RocketPlay Casino",
        "trustpilot_domain": "rocketplay.com",
        "askgamblers_slug": "rocketplay-casino",
        "casinoguru_slug": "rocketplay-casino-review",
    },
    "only_win": {
        "name": "OnlyWin Casino",
        "trustpilot_domain": "onlywinss.com",      # only.win returns 0 — use this domain
        "askgamblers_slug": "onlywin-casino",       # no dash between "only" and "win"
        "casinoguru_slug": "onlywin-casino-review", # no dash between "only" and "win"
    },
}

APIFY_BASE = "https://api.apify.com/v2/acts"

# ---------------------------------------------------------------------------
# Mock data — realistic reviews with intentional variety for demo
# ---------------------------------------------------------------------------

def get_mock_data() -> list[dict]:
    today = date.today().isoformat()
    return [
        {
            "brand": "lucky_dreams",
            "brand_name": "Lucky Dreams Casino",
            "platform": "trustpilot",
            "id": "mock_ld_001",
            "reviewer": "Michael T.",
            "date": today,
            "rating": 1,
            "title": "Account blocked right after winning",
            "text": "Won 2,400 EUR, immediately got account blocked. Support keeps saying 'under review' for 2 weeks. Classic scam pattern. AVOID.",
            "url": "https://trustpilot.com/reviews/mock_ld_001",
        },
        {
            "brand": "lucky_dreams",
            "brand_name": "Lucky Dreams Casino",
            "platform": "askgamblers",
            "id": "mock_ld_002",
            "reviewer": "Sandra K.",
            "date": today,
            "rating": 4,
            "title": "Great game variety, withdrawal could be faster",
            "text": "Love the slot selection and live casino. Withdrew 800 EUR, took 4 days via bank transfer. Could be quicker but overall satisfied.",
            "url": "https://askgamblers.com/mock_ld_002",
        },
        {
            "brand": "rocket_play",
            "brand_name": "RocketPlay Casino",
            "platform": "trustpilot",
            "id": "mock_rp_001",
            "reviewer": "James O.",
            "date": today,
            "rating": 5,
            "title": "Best casino I've used in years",
            "text": "Fast payouts every time, live chat actually helpful. VIP treatment even at mid-level. Highly recommend.",
            "url": "https://trustpilot.com/reviews/mock_rp_001",
        },
        {
            "brand": "rocket_play",
            "brand_name": "RocketPlay Casino",
            "platform": "casinoguru",
            "id": "mock_rp_002",
            "reviewer": "Elena M.",
            "date": today,
            "rating": 2,
            "title": "Bonus wagering terms changed without notice",
            "text": "Had 500 EUR in bonus balance, wagering requirement suddenly changed from 30x to 45x. No notification. Lost everything trying to clear it. Disappointed.",
            "url": "https://casino.guru/mock_rp_002",
        },
        {
            "brand": "only_win",
            "brand_name": "OnlyWin Casino",
            "platform": "trustpilot",
            "id": "mock_ow_001",
            "reviewer": "David R.",
            "date": today,
            "rating": 1,
            "title": "Deposit missing for 10 days",
            "text": "Deposited 200 GBP via bank transfer 10 days ago. Casino claims they haven't received it, my bank confirms it left my account. Support is useless.",
            "url": "https://trustpilot.com/reviews/mock_ow_001",
        },
        {
            "brand": "only_win",
            "brand_name": "OnlyWin Casino",
            "platform": "askgamblers",
            "id": "mock_ow_002",
            "reviewer": "Priya S.",
            "date": today,
            "rating": 3,
            "title": "Good games, KYC process too slow",
            "text": "Game selection is excellent, especially live dealer tables. However KYC verification took 6 days which delayed my first withdrawal significantly.",
            "url": "https://askgamblers.com/mock_ow_002",
        },
    ]


# ---------------------------------------------------------------------------
# Apify API
# ---------------------------------------------------------------------------

def apify_run(actor_id: str, input_data: dict, token: str, timeout: int = 120) -> list:
    """Run Apify actor synchronously and return dataset items."""
    actor_path = actor_id.replace("/", "~")
    url = f"{APIFY_BASE}/{actor_path}/run-sync-get-dataset-items"
    resp = requests.post(
        url,
        json=input_data,
        params={"token": token, "timeout": timeout},
        timeout=timeout + 15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_trustpilot(raw: dict) -> dict:
    """Map Apify blackfalcondata/trustpilot-reviews-scraper output → unified review schema."""
    return {
        "platform":  "trustpilot",
        "id":        raw.get("reviewId", ""),
        "reviewer":  raw.get("reviewerName", ""),
        "date":      raw.get("publishedDate", ""),
        "rating":    int(raw.get("rating", 0) or 0),
        "title":     raw.get("title", ""),
        "text":      raw.get("text", ""),
        "url":       raw.get("reviewUrl", ""),
    }


def review_fingerprint(platform: str, reviewer: str, text: str) -> str:
    """Stable ID for deduplication when native ID is not available."""
    raw = f"{platform}:{reviewer}:{text[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_trustpilot_reviews(domain: str, token: str, limit: int = 20) -> list[dict]:
    # blackfalcondata actor: FREE, stops at maxResults (page-by-page), no timeout for large profiles
    items = apify_run(
        "blackfalcondata/trustpilot-reviews-scraper",
        {
            "companyDomain": domain,
            "maxResults": limit,
            "sort": "recency",
            "compact": True,
        },
        token,
    )
    return [normalize_trustpilot(item) for item in items]


def fetch_page_markdown(url: str, token: str) -> str:
    """Fetch a review page via rag-web-browser and return its markdown."""
    items = apify_run(
        "apify/rag-web-browser",
        {"query": url},
        token,
        timeout=90,
    )
    return items[0].get("markdown", "") if items else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        if os.environ.get("REVIEWS_MOCK") == "true":
            print(json.dumps(get_mock_data()))
            return

        token = os.environ["APIFY_API_TOKEN"]
        all_reviews: list[dict] = []

        for brand_key, brand in BRANDS.items():
            # --- Trustpilot (structured JSON) ---
            if brand.get("trustpilot_domain"):
                try:
                    reviews = fetch_trustpilot_reviews(brand["trustpilot_domain"], token)
                    for r in reviews:
                        r["brand"] = brand_key
                        r["brand_name"] = brand["name"]
                        all_reviews.append(r)
                except Exception as e:
                    print(f"WARN trustpilot/{brand_key}: {e}", file=sys.stderr)

            # --- AskGamblers (Google search query to bypass 403 on direct URLs) ---
            if brand.get("askgamblers_slug"):
                try:
                    ag_url = f"https://www.askgamblers.com/online-casinos/reviews/{brand['askgamblers_slug']}"
                    # Pass search query, not direct URL — direct AskGamblers URLs return 403
                    ag_query = f"{brand['name']} reviews site:askgamblers.com"
                    markdown = fetch_page_markdown(ag_query, token)
                    if markdown and "Page not found" not in markdown[:500]:
                        all_reviews.append({
                            "brand": brand_key,
                            "brand_name": brand["name"],
                            "platform": "askgamblers",
                            "format": "markdown_page",
                            "markdown": markdown[:8000],  # cap to avoid token overflow
                            "url": ag_url,
                        })
                except Exception as e:
                    print(f"WARN askgamblers/{brand_key}: {e}", file=sys.stderr)

            # --- CasinoGuru (markdown — Claude will parse in Routine) ---
            if brand.get("casinoguru_slug"):
                try:
                    cg_url = f"https://casino.guru/{brand['casinoguru_slug']}"
                    markdown = fetch_page_markdown(cg_url, token)
                    if markdown and "Page not found" not in markdown[:500]:
                        all_reviews.append({
                            "brand": brand_key,
                            "brand_name": brand["name"],
                            "platform": "casinoguru",
                            "format": "markdown_page",
                            "markdown": markdown[:8000],
                            "url": cg_url,
                        })
                except Exception as e:
                    print(f"WARN casinoguru/{brand_key}: {e}", file=sys.stderr)

        print(json.dumps(all_reviews))

    except KeyError as e:
        print(f"ERROR: missing env var {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

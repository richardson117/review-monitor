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
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

MARKDOWN_CAP = 5000  # chars per page (was 8000) — halves Claude's input tokens

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


def fetch_page_markdown(query: str, token: str, *, use_browser: bool = False) -> str:
    """Fetch a page via rag-web-browser and return its markdown.

    Set use_browser=True to use Playwright (slower ~30-60s but bypasses
    Cloudflare/anti-bot — required for AskGamblers).
    """
    input_data: dict = {"query": query}
    timeout = 90
    if use_browser:
        input_data["scrapingTool"] = "browser-playwright"
        input_data["dynamicContentWaitSecs"] = 10
        timeout = 180
    items = apify_run("apify/rag-web-browser", input_data, token, timeout=timeout)
    return items[0].get("markdown", "") if items else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _cov(brand_key: str, brand_name: str, platform: str, status: str, **kw) -> dict:
    """Build a coverage record. status: 'ok' | 'empty' | 'error' | 'not_configured'."""
    return {"brand": brand_key, "brand_name": brand_name, "platform": platform,
            "status": status, **kw}


def _markdown_result(brand_key: str, brand_name: str, platform: str,
                     url: str, markdown: str) -> tuple[list, dict]:
    """Convert raw markdown into (reviews, coverage). Empty/404 → no review."""
    if not markdown:
        return [], _cov(brand_key, brand_name, platform, "error",
                        error="empty_response", url=url)
    head = markdown[:500]
    if "Page not found" in head or "Error 404" in head:
        return [], _cov(brand_key, brand_name, platform, "empty",
                        reason="not_listed", url=url)
    review = {"brand": brand_key, "brand_name": brand_name, "platform": platform,
              "format": "markdown_page", "markdown": markdown[:MARKDOWN_CAP], "url": url}
    return [review], _cov(brand_key, brand_name, platform, "ok", url=url)


def _fetch_trustpilot(brand_key: str, brand: dict, token: str) -> tuple[list, dict]:
    name = brand["name"]
    domain = brand.get("trustpilot_domain")
    if not domain:
        return [], _cov(brand_key, name, "trustpilot", "not_configured")
    try:
        reviews = fetch_trustpilot_reviews(domain, token)
        for r in reviews:
            r["brand"] = brand_key
            r["brand_name"] = name
        return reviews, _cov(brand_key, name, "trustpilot",
                             "ok" if reviews else "empty", count=len(reviews))
    except Exception as e:
        print(f"WARN trustpilot/{brand_key}: {e}", file=sys.stderr)
        return [], _cov(brand_key, name, "trustpilot", "error", error=str(e)[:200])


def _fetch_askgamblers(brand_key: str, brand: dict, token: str) -> tuple[list, dict]:
    name = brand["name"]
    slug = brand.get("askgamblers_slug")
    if not slug:
        return [], _cov(brand_key, name, "askgamblers", "not_configured")
    url = f"https://www.askgamblers.com/online-casinos/reviews/{slug}"
    try:
        # AskGamblers blocks raw-http (Cloudflare); browser-playwright passes the JS challenge
        markdown = fetch_page_markdown(url, token, use_browser=True)
        return _markdown_result(brand_key, name, "askgamblers", url, markdown)
    except Exception as e:
        print(f"WARN askgamblers/{brand_key}: {e}", file=sys.stderr)
        return [], _cov(brand_key, name, "askgamblers", "error",
                        error=str(e)[:200], url=url)


def _fetch_casinoguru(brand_key: str, brand: dict, token: str) -> tuple[list, dict]:
    name = brand["name"]
    slug = brand.get("casinoguru_slug")
    if not slug:
        return [], _cov(brand_key, name, "casinoguru", "not_configured")
    url = f"https://casino.guru/{slug}"
    try:
        markdown = fetch_page_markdown(url, token)
        return _markdown_result(brand_key, name, "casinoguru", url, markdown)
    except Exception as e:
        print(f"WARN casinoguru/{brand_key}: {e}", file=sys.stderr)
        return [], _cov(brand_key, name, "casinoguru", "error",
                        error=str(e)[:200], url=url)


def main() -> None:
    try:
        if os.environ.get("REVIEWS_MOCK") == "true":
            mock_reviews = get_mock_data()
            mock_coverage = [
                {"brand": r["brand"], "brand_name": r["brand_name"],
                 "platform": r["platform"], "status": "ok", "count": 1}
                for r in mock_reviews
            ]
            print(json.dumps({"reviews": mock_reviews, "coverage": mock_coverage}))
            return

        token = os.environ["APIFY_API_TOKEN"]

        # Build 9 tasks (3 brands × 3 platforms) and run in parallel.
        # Without parallelism this would be ~3 min (AskGamblers Playwright is slow).
        # With parallelism it's bounded by the slowest single call (~60s).
        tasks = []
        for brand_key, brand in BRANDS.items():
            tasks.append((_fetch_trustpilot, brand_key, brand))
            tasks.append((_fetch_askgamblers, brand_key, brand))
            tasks.append((_fetch_casinoguru, brand_key, brand))

        all_reviews: list[dict] = []
        coverage: list[dict] = []
        with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            futures = [ex.submit(fn, bk, b, token) for fn, bk, b in tasks]
            for f in futures:
                reviews, cov = f.result()
                all_reviews.extend(reviews)
                coverage.append(cov)

        print(json.dumps({"reviews": all_reviews, "coverage": coverage}))

    except KeyError as e:
        print(f"ERROR: missing env var {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

@~/.claude/rules/discipline.md

# Review Monitor

Fetches recent reviews for casino brands from Trustpilot, AskGamblers, and CasinoGuru via Apify.
Outputs a JSON object `{reviews: [...], coverage: [...]}` for Claude to analyse → Slack digest.

## Env vars

| Variable | Required | Description |
|---|---|---|
| `APIFY_API_TOKEN` | Real mode only | From apify.com → Settings → API tokens |
| `SLACK_WEBHOOK_URL` | For Slack delivery | Slack Incoming Webhook URL |
| `REVIEWS_MOCK` | No | Set to `true` to skip Apify calls (demo/dev) |

## Run

```powershell
cd "C:/Dev/new tools/review-monitor"

# Mock mode — no credentials needed (always works)
$env:REVIEWS_MOCK="true"
python scripts/fetch_reviews.py

# Real mode
$env:APIFY_API_TOKEN="apify_api_..."
python scripts/fetch_reviews.py
```

## Tests

```powershell
pytest tests/ -v
```

All 18 tests must be green before any commit.

---

## Platform notes — READ BEFORE CHANGING ANYTHING

### Trustpilot
- **Actor**: `blackfalcondata/trustpilot-reviews-scraper` (FREE, no cost per review)
- **Input**: `{"companyDomain": "domain.com", "maxResults": 20, "sort": "recency", "compact": True}`
- Fetches page-by-page, stops at `maxResults` → fast even for large profiles (RocketPlay has 312 reviews)
- **DO NOT switch back to `getwally.net/trustpilot-reviews-scraper`** — it loads ALL reviews before
  applying limit, causing 300s timeout on large profiles
- Output fields: `reviewId`, `reviewerName`, `publishedDate`, `rating` (int), `title`, `text`, `reviewUrl`

### AskGamblers
- **Actor**: `apify/rag-web-browser` with `scrapingTool: "browser-playwright"`
- **IMPORTANT**: AskGamblers is behind Cloudflare. Default `raw-http` returns 403.
  - Solution: switch to Playwright (real Chromium) which passes the JS challenge → HTTP 200
  - Slower (~30-60s per page) but reliable
- **Direct URL works fine** with Playwright, no need for Google search workaround
- **Input**: `{"query": "https://www.askgamblers.com/online-casinos/reviews/<slug>", "scrapingTool": "browser-playwright", "dynamicContentWaitSecs": 10}`
- In `fetch_reviews.py`: call `fetch_page_markdown(url, token, use_browser=True)`

### CasinoGuru
- **Actor**: `apify/rag-web-browser`
- Direct URL works fine (no anti-scraping), HTTP 200
- **Input**: `{"query": "https://casino.guru/lucky-dreams-casino-review", "maxResults": 1}`
- Returns 60KB+ markdown with reviews, provider list, bonuses

---

## Brand config (BRANDS dict in fetch_reviews.py)

| Brand key | Trustpilot domain | AskGamblers slug | CasinoGuru slug |
|---|---|---|---|
| `lucky_dreams` | `luckydreams.com` | `lucky-dreams-casino` | `lucky-dreams-casino-review` |
| `rocket_play` | `rocketplay.com` | `rocketplay-casino` | `rocketplay-casino-review` |
| `only_win` | `onlywinss.com` | `onlywin-casino` | `onlywin-casino-review` |

All slugs confirmed live (April 2026).

**OnlyWin gotchas**:
- Trustpilot: `only.win` returns 0 reviews → use `onlywinss.com`
- AskGamblers / CasinoGuru: slug is `onlywin-casino` / `onlywin-casino-review` (no dash, not `only-win-...`)

## Adding a new brand

1. Add entry to `BRANDS` dict in `scripts/fetch_reviews.py`
2. Add 2 mock reviews to `get_mock_data()` (keeps test coverage intact)
3. Run `pytest tests/ -v` — all tests must stay green

---

## Customizing brands via Claude Code session (FOR THE AI AGENT)

When a user says **"add brand X"** / **"monitor brand X"** / **"replace OnlyWin with Y"**:

### Step 1 — Discover URLs (use rag-web-browser via Apify MCP if available, otherwise WebSearch)

For each of the 3 platforms, run a Google site-search:
- Trustpilot: `<brand> reviews site:trustpilot.com` → extract domain from URL `trustpilot.com/review/<DOMAIN>`
- AskGamblers: `<brand> casino site:askgamblers.com` → extract slug from URL `/reviews/<SLUG>`
- CasinoGuru: `<brand> casino review site:casino.guru` → extract slug from URL `casino.guru/<SLUG>` (usually ends in `-review`)

### Step 2 — If a platform returns nothing, 404, or an unrelated page

**DO NOT GUESS the slug.** Ask the user directly:

> "I couldn't find `<brand>` on `<platform>`. Could you paste the brand's profile URL
> from `<platform>`? Or say `skip <platform>` if it's not listed there."

User pastes the URL → extract the slug from it → continue.
User says skip → set `<platform>_slug: None` in BRANDS, the `main()` loop already handles None gracefully.

### Step 3 — Update code

1. Update `BRANDS` dict in `scripts/fetch_reviews.py`
2. Add 2 realistic mock reviews to `get_mock_data()` (one negative, one positive — match the existing pattern)
3. Run `pytest tests/ -v` — must be 17/17 green (or 17 + new brand mock-data tests)

### Step 4 — Commit and push

```
git checkout -b add-<brand-slug>
git add scripts/fetch_reviews.py
git commit -m "Add <Brand Name> to monitored brands"
git push -u origin add-<brand-slug>
```

The next scheduled Routine run will pick up the new brand automatically.

### Brand removal

Same flow but delete the entry from `BRANDS` and remove its mock reviews from `get_mock_data()`.

---

## Routine Environment requirements (for reference)

When setting up the Custom Environment in claude.ai/code:

**Network access (Custom):**
- Default package managers: ✅ keep enabled (for pip)
- Allowed domains:
  ```
  api.apify.com
  hooks.slack.com
  www.trustpilot.com
  www.askgamblers.com
  casino.guru
  ```

**Env vars:**
```
APIFY_API_TOKEN=apify_api_xxx
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/.../.../...
```

**Setup script:**
```bash
#!/bin/bash
pip install -r scripts/requirements.txt || true
```

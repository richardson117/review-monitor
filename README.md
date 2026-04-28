# Review Monitor

Automated casino review monitoring: Trustpilot + AskGamblers + CasinoGuru → AI sentiment/urgency analysis → Slack digest.

Built for the **iGaming AI Pipelines** workshop. Runs on Claude Code Routines (cloud cron — works while you sleep).

---

## What it does

Every morning (or hourly), Claude:

1. Fetches latest reviews for **3 brands** across **3 platforms** via Apify
2. Classifies each review by:
   - **Urgency**: 🔴 (critical: 1-2★ with payment/account issues) / 🟡 (mixed: 3★ or UX/bonus issues) / 🟢 (positive: 4-5★)
   - **Theme**: payments / support / UX-bonus / positive / other
3. Sends a digest to your Slack channel

**Default brands:** Lucky Dreams, RocketPlay, OnlyWin (you can add your own — see "Customizing" below).

---

## Quick start (~15 minutes)

### 1. Use this template

Click the green **"Use this template"** button at the top of this repo → "Create a new repository" → choose Public/Private → name it (e.g. `review-monitor`).

You now own a copy of all the code, decoupled from this template.

### 2. Get your credentials

| Service | What you need | How |
|---|---|---|
| **Apify** | API token | apify.com → Sign up (free, $5 credits) → Settings → API tokens → Copy |
| **Slack** | Incoming Webhook URL | Slack workspace → Apps → Incoming Webhooks → Add to channel → Copy URL |

Keep these in a safe place (password manager). Never commit them.

### 3. Set up Custom Environment in Claude Code

Go to **claude.ai/code** → top-left dropdown → **Add environment**:

- **Name:** `review-monitor-env`
- **Network access:** Custom
  - ✅ Also include default list of common package managers
  - Allowed domains (one per line):
    ```
    api.apify.com
    hooks.slack.com
    www.trustpilot.com
    www.askgamblers.com
    casino.guru
    ```
- **Environment variables:**
  ```
  APIFY_API_TOKEN=apify_api_xxxxxxxxx
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
  ```
- **Setup script:**
  ```bash
  #!/bin/bash
  pip install -r scripts/requirements.txt || true
  ```
- Save

### 4. Create the Routine

Go to **claude.ai/code/routines** → **New routine**:

- **Name:** Review Monitor Daily
- **Repository:** select your forked repo (`<your-username>/review-monitor`)
- **Environment:** `review-monitor-env`
- **Trigger:** Schedule → Daily → 09:00 (your local time)
- **Prompt:** copy the entire content of [`ROUTINE_PROMPT.md`](./ROUTINE_PROMPT.md) into the Prompt field

### 5. Test it

Click **Run now** → wait ~1-2 min → check your Slack channel.

You should see a digest like:
```
📋 Review Monitor | Lucky Dreams / RocketPlay / OnlyWin
6 reviews across 3 platforms

🔴 Trustpilot ⭐ — Lucky Dreams — "Account blocked..."  → payments
🟡 CasinoGuru ⭐⭐ — RocketPlay — "Bonus terms changed..." → bonus
🟢 Trustpilot ⭐⭐⭐⭐⭐ — RocketPlay — "Best casino..." → positive
```

If it works — congrats, you have a self-running AI pipeline. The Routine will fire daily on its own.

---

## Customizing brands

Want to monitor your own brand or competitors? You don't need to write any code.

1. Open your forked repo in **claude.ai/code** (Open repository button)
2. In the chat, say: **"Add Stake Casino to brands"** (or `replace OnlyWin with X`, `remove RocketPlay`, etc.)
3. Claude will:
   - Search for the brand on Trustpilot / AskGamblers / CasinoGuru
   - If it can't find a slug — **ask you for the URL** (just paste the brand's profile URL from that platform)
   - Update the code, run tests, commit, push to your repo
4. The next scheduled Routine run automatically uses the new brands

**That's the whole UX.** Talk to Claude in plain English; it does the rest.

---

## Local development

```powershell
# Install
pip install -r scripts/requirements.txt

# Mock mode — no credentials needed (uses fake reviews)
$env:REVIEWS_MOCK="true"
python scripts/fetch_reviews.py

# Real mode — needs APIFY_API_TOKEN
$env:APIFY_API_TOKEN="apify_api_..."
python scripts/fetch_reviews.py

# Tests
pytest tests/ -v
```

All 17 tests must stay green. They run in ~1 second and don't hit any external API.

---

## Architecture

```
Routine (cron, daily 9am)
    ↓
Claude reads BRANDS dict from scripts/fetch_reviews.py
    ↓
Claude runs: python scripts/fetch_reviews.py
    ↓
Python script:
  ├─ Apify: blackfalcondata/trustpilot-reviews-scraper (FREE) → structured JSON
  ├─ Apify: rag-web-browser (Google search) → AskGamblers markdown
  └─ Apify: rag-web-browser → CasinoGuru markdown
    ↓
JSON to stdout
    ↓
Claude analyzes (urgency / theme classification)
    ↓
Claude formats Slack message → POST to SLACK_WEBHOOK_URL
```

**Key design choice:** Python script is a *pure data fetcher* (deterministic, testable). All AI work happens in the Routine runtime.

---

## Files

```
review-monitor/
├── scripts/
│   ├── fetch_reviews.py    # main fetcher — BRANDS dict at top
│   └── requirements.txt
├── tests/
│   ├── conftest.py
│   ├── __init__.py
│   └── test_fetch_reviews.py    # 17 tests, run before any commit
├── .env.example                  # copy to .env for local dev
├── .gitignore
├── CLAUDE.md                     # instructions for the AI agent
├── README.md                     # this file
└── ROUTINE_PROMPT.md             # copy-paste into Routine UI
```

---

## Cost estimate

- **Apify**: blackfalcondata Trustpilot is FREE; rag-web-browser ~$0.005/page → ~$0.04/run for 3 brands × 2 markdown pages
- **Claude Routines**: included in your plan
- **Slack**: free

Daily run = **~$0.04**. Monthly = **~$1.20**. Free $5 Apify credit covers ~125 runs.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: requests` | Setup script didn't run | Check Environment → Setup script field |
| `KeyError: 'APIFY_API_TOKEN'` | Env var not set | Re-check Environment → Env vars |
| Slack message not arriving | `hooks.slack.com` not in allowed domains | Add to Network access |
| 0 reviews from Trustpilot | Domain wrong | Edit BRANDS in fetch_reviews.py — check trustpilot.com/review/&lt;domain&gt; |
| All platforms 0 for one brand | Brand not listed there | Ask Claude to skip that platform for that brand |

For anything else — open the Routine session URL → see Claude's full reasoning + bash output.

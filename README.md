# Portfolio Automation Pipeline

Automated system that keeps your portfolio website synced with your GitHub, X (Twitter), and LinkedIn activity.

## How It Works

| Platform | Automation Level | How |
| :--- | :--- | :--- |
| **GitHub** | 🟢 Fully Automated | Fetches all public repos every 24h via GitHub API |
| **X (Twitter)** | 🟡 Semi-Automated | You paste tweet URLs → system fetches embed data via oEmbed API |
| **LinkedIn** | 🟡 Semi-Automated | You paste post URLs → system renders as embed cards |

## Quick Start

### 1. Add a Social Post (30 seconds)

Edit `data/social_posts.json` and add your post URL:

```json
[
  {
    "url": "https://x.com/AtharvPorwal0/status/YOUR_TWEET_ID",
    "added_on": "2026-08-19"
  },
  {
    "url": "https://www.linkedin.com/posts/atharv-porwal-549526283_YOUR_POST_SLUG",
    "added_on": "2026-08-19"
  }
]
```

Commit and push — the automation handles everything else.

### 2. GitHub Repos (Zero Effort)

Your public repos are fetched automatically every 24 hours. No action needed.

## Setup (One-Time)

### Prerequisites
- GitHub account with this repo
- Python 3.10+ (for local testing only)

### GitHub Repository Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value | Required? |
| :--- | :--- | :--- |
| `GH_PAT` | Your GitHub Personal Access Token (with `repo`, `read:user` scopes) | Recommended (increases API rate limit from 60 to 5000 req/hr) |
| `SITE_URL` | Your deployed site URL (e.g., `https://atharvporwal.vercel.app`) | Optional (enables live site verification) |

### Generate a GitHub Personal Access Token

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Name: `portfolio-automation`
4. Expiration: No expiration (or 1 year)
5. Scopes: ✅ `repo`, ✅ `read:user`
6. Click **Generate token** → Copy it
7. Add it as repository secret `GH_PAT`

## Project Structure

```
├── .github/workflows/
│   ├── sync.yml          # Runs every 24h: fetches data, processes URLs
│   └── verify.yml        # Runs after sync: verifies posts are live
├── scripts/
│   ├── fetch_github.py   # Fetches GitHub profile + repos
│   ├── process_social.py # Processes X/LinkedIn URLs into embed data
│   └── verify_posts.py   # Verifies posts appear on live site
├── data/
│   ├── social_posts.json # YOU EDIT THIS: paste your post URLs
│   ├── github.json       # Auto-generated: GitHub repos data
│   ├── feed.json         # Auto-generated: processed social feed
│   └── archive.json      # Auto-generated: historical post archive
├── requirements.txt
└── README.md
```

## Automated Workflows

### Sync (every 24 hours)
- Fetches your latest GitHub repos and profile
- Processes any new URLs in `social_posts.json`
- Commits updated JSON files → triggers site rebuild

### Verify (after each sync)
- Checks that all posts are present in `feed.json`
- Verifies original post URLs are still accessible
- Checks live site (if `SITE_URL` is configured)
- Sends email alert if any check fails

## Local Testing

```bash
# Test GitHub fetcher
python scripts/fetch_github.py

# Test social processor (add some URLs to data/social_posts.json first)
python scripts/process_social.py

# Test verification
python scripts/verify_posts.py
```

## Cost

| Component | Monthly Cost |
| :--- | :--- |
| GitHub Actions | $0 |
| GitHub API | $0 |
| X oEmbed API | $0 |
| Hosting (Vercel/GitHub Pages) | $0 |
| **Total** | **$0.00** |

---

Built with ❤️ for [AtharvPorwal](https://github.com/AtharvPorwal)

"""
fetch_github.py — Fetches public GitHub profile and repo data for portfolio.

Runs on GitHub Actions every 24 hours (or locally for testing).
Writes output to data/github.json.

Usage:
    python scripts/fetch_github.py

Environment variables (optional):
    GITHUB_TOKEN — Personal Access Token for higher rate limits (5000 req/hr vs 60 req/hr).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# === Configuration ===
GITHUB_USERNAME = "AtharvPorwal"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "github.json"
API_BASE = "https://api.github.com"


def make_request(url: str, token: str | None = None) -> dict | list:
    """Make an authenticated (or unauthenticated) request to the GitHub API."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PortfolioAutomation/1.0",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"ERROR: GitHub API returned {e.code} for {url}")
        print(f"  Response: {e.read().decode('utf-8', errors='replace')[:500]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Could not reach GitHub API — {e.reason}")
        sys.exit(1)


def fetch_user_profile(token: str | None = None) -> dict:
    """Fetch the user's public profile information."""
    url = f"{API_BASE}/users/{GITHUB_USERNAME}"
    data = make_request(url, token)
    return {
        "name": data.get("name") or GITHUB_USERNAME,
        "login": data.get("login", GITHUB_USERNAME),
        "bio": data.get("bio", ""),
        "avatar_url": data.get("avatar_url", ""),
        "html_url": data.get("html_url", f"https://github.com/{GITHUB_USERNAME}"),
        "public_repos": data.get("public_repos", 0),
        "followers": data.get("followers", 0),
        "following": data.get("following", 0),
        "location": data.get("location", ""),
        "blog": data.get("blog", ""),
        "twitter_username": data.get("twitter_username", ""),
        "created_at": data.get("created_at", ""),
    }


def fetch_all_repos(token: str | None = None) -> list[dict]:
    """Fetch all public repos with pagination support (up to 300 repos)."""
    all_repos = []
    page = 1
    per_page = 100  # max allowed by GitHub

    while page <= 3:  # safety limit: 3 pages = 300 repos
        url = (
            f"{API_BASE}/users/{GITHUB_USERNAME}/repos"
            f"?type=public&sort=updated&direction=desc"
            f"&per_page={per_page}&page={page}"
        )
        repos = make_request(url, token)

        if not repos:
            break  # no more repos

        for repo in repos:
            # Skip forks unless they have significant stars
            if repo.get("fork") and repo.get("stargazers_count", 0) < 2:
                continue

            all_repos.append({
                "name": repo.get("name", ""),
                "description": repo.get("description", "") or "No description provided.",
                "url": repo.get("html_url", ""),
                "homepage": repo.get("homepage", ""),
                "language": repo.get("language", ""),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "watchers": repo.get("watchers_count", 0),
                "open_issues": repo.get("open_issues_count", 0),
                "topics": repo.get("topics", []),
                "is_fork": repo.get("fork", False),
                "created_at": repo.get("created_at", ""),
                "updated_at": repo.get("updated_at", ""),
                "pushed_at": repo.get("pushed_at", ""),
                "size_kb": repo.get("size", 0),
                "default_branch": repo.get("default_branch", "main"),
                "license": (repo.get("license") or {}).get("spdx_id", ""),
            })

        if len(repos) < per_page:
            break  # this was the last page

        page += 1

    return all_repos


def fetch_repo_languages(repo_name: str, token: str | None = None) -> dict:
    """Fetch the language breakdown for a specific repo."""
    url = f"{API_BASE}/repos/{GITHUB_USERNAME}/{repo_name}/languages"
    try:
        return make_request(url, token)
    except SystemExit:
        # Non-critical: if this fails, just return empty
        return {}


def main():
    """Main entry point: fetch all data and write to JSON."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    if token:
        print(f"Using authenticated GitHub API (higher rate limits).")
    else:
        print(f"Using unauthenticated GitHub API (60 requests/hour limit).")
        print(f"  Tip: Set GITHUB_TOKEN env var for 5000 requests/hour.")

    # Fetch profile
    print(f"\nFetching profile for @{GITHUB_USERNAME}...")
    profile = fetch_user_profile(token)
    print(f"  Name: {profile['name']}")
    print(f"  Public repos: {profile['public_repos']}")
    print(f"  Followers: {profile['followers']}")

    # Fetch repos
    print(f"\nFetching public repositories...")
    repos = fetch_all_repos(token)
    print(f"  Found {len(repos)} repos (excluding low-star forks).")

    # Fetch language breakdowns for top repos (by most recently updated)
    top_repos = repos[:10]  # only fetch languages for top 10 to save API calls
    print(f"\nFetching language breakdowns for top {len(top_repos)} repos...")
    for repo in top_repos:
        languages = fetch_repo_languages(repo["name"], token)
        if languages:
            total_bytes = sum(languages.values())
            repo["languages"] = {
                lang: round(bytes_count / total_bytes * 100, 1)
                for lang, bytes_count in languages.items()
            }
        else:
            repo["languages"] = {}

    # Calculate aggregate stats
    all_languages = {}
    for repo in repos:
        lang = repo.get("language")
        if lang:
            all_languages[lang] = all_languages.get(lang, 0) + 1

    total_stars = sum(r["stars"] for r in repos)
    total_forks = sum(r["forks"] for r in repos)

    # Build output
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "github_username": GITHUB_USERNAME,
        "profile": profile,
        "stats": {
            "total_repos": len(repos),
            "total_stars": total_stars,
            "total_forks": total_forks,
            "languages_used": dict(
                sorted(all_languages.items(), key=lambda x: x[1], reverse=True)
            ),
        },
        "repos": repos,
    }

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] GitHub data written to {OUTPUT_FILE}")
    print(f"     {len(repos)} repos | {total_stars} stars | {len(all_languages)} languages")


if __name__ == "__main__":
    main()

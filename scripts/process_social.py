"""
process_social.py — Processes social media post URLs for portfolio embedding.

Reads data/social_posts.json (URLs you manually paste) and:
  - For Twitter/X posts: calls the free oEmbed API to get embed HTML
  - For LinkedIn posts: generates embed card data (LinkedIn iframe embed)

Writes output to data/feed.json.

Usage:
    python scripts/process_social.py
"""

import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# === Configuration ===
INPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "social_posts.json"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "feed.json"
ARCHIVE_FILE = Path(__file__).resolve().parent.parent / "data" / "archive.json"

X_OEMBED_URL = "https://publish.twitter.com/oembed"


def load_social_posts() -> list[dict]:
    """Load the user-maintained list of social post URLs."""
    if not INPUT_FILE.exists():
        print(f"WARNING: {INPUT_FILE} not found. Creating empty template.")
        INPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INPUT_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return []

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        try:
            posts = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in {INPUT_FILE}: {e}")
            sys.exit(1)

    if not isinstance(posts, list):
        print(f"ERROR: {INPUT_FILE} must contain a JSON array.")
        sys.exit(1)

    return posts


def load_existing_feed() -> dict:
    """Load the existing feed.json to preserve previously processed posts."""
    if not OUTPUT_FILE.exists():
        return {"last_updated": None, "posts": []}

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"last_updated": None, "posts": []}


def load_archive() -> list[dict]:
    """Load the historical archive of all processed posts."""
    if not ARCHIVE_FILE.exists():
        return []

    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication (strip trailing slashes, lowercase domain)."""
    url = url.strip().rstrip("/")
    # Normalize x.com / twitter.com
    url = url.replace("https://twitter.com/", "https://x.com/")
    url = url.replace("http://twitter.com/", "https://x.com/")
    url = url.replace("http://x.com/", "https://x.com/")
    return url


def detect_platform(url: str) -> str:
    """Detect the platform from a URL."""
    url_lower = url.lower()
    if "x.com/" in url_lower or "twitter.com/" in url_lower:
        return "twitter"
    elif "linkedin.com/" in url_lower:
        return "linkedin"
    else:
        return "unknown"


def fetch_twitter_oembed(tweet_url: str) -> dict | None:
    """
    Call the X/Twitter oEmbed API to get embed HTML for a tweet.
    This API is free and does not require authentication.
    """
    params = urllib.parse.urlencode({
        "url": tweet_url,
        "omit_script": "true",  # we'll load the widget.js once in the page
        "hide_thread": "false",
        "dnt": "true",  # do not track
    })
    url = f"{X_OEMBED_URL}?{params}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "PortfolioAutomation/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "embed_html": data.get("html", ""),
                "author_name": data.get("author_name", ""),
                "author_url": data.get("author_url", ""),
                "provider_name": data.get("provider_name", "Twitter"),
                "cache_age": data.get("cache_age", ""),
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ⚠️  Tweet not found (may be deleted): {tweet_url}")
            return {"error": "not_found", "message": "Tweet not found or deleted."}
        elif e.code == 403:
            print(f"  ⚠️  Tweet is from a private/suspended account: {tweet_url}")
            return {"error": "forbidden", "message": "Tweet is private or account suspended."}
        else:
            print(f"  ⚠️  oEmbed API error {e.code} for: {tweet_url}")
            return {"error": f"http_{e.code}", "message": str(e)}
    except urllib.error.URLError as e:
        print(f"  ⚠️  Network error fetching oEmbed: {e.reason}")
        return {"error": "network_error", "message": str(e.reason)}
    except Exception as e:
        print(f"  ⚠️  Unexpected error: {e}")
        return {"error": "unexpected", "message": str(e)}


def process_linkedin_post(post_url: str) -> dict:
    """
    Generate embed data for a LinkedIn post.
    LinkedIn doesn't have a public oEmbed API, so we generate an iframe embed URL
    and a direct link card.
    """
    # LinkedIn embed format: convert the post URL to an embeddable iframe src
    # LinkedIn supports embedding via: https://www.linkedin.com/embed/feed/update/<urn>
    # But for generic post URLs, we use the direct link approach.

    return {
        "embed_type": "linkedin-card",
        "embed_url": post_url,
        "provider_name": "LinkedIn",
        # The website will render this as a styled card with a "View on LinkedIn" link
        # and optionally use LinkedIn's embed iframe if the URL format supports it.
    }


def process_post(post: dict) -> dict:
    """Process a single social post entry and enrich it with embed data."""
    url = normalize_url(post.get("url", ""))

    if not url:
        return {**post, "status": "error", "error": "Missing URL"}

    # Auto-detect platform if not specified
    platform = post.get("platform") or detect_platform(url)

    result = {
        "platform": platform,
        "url": url,
        "added_on": post.get("added_on", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    if platform == "twitter":
        print(f"  Fetching oEmbed for tweet: {url}")
        oembed_data = fetch_twitter_oembed(url)
        if oembed_data and "error" not in oembed_data:
            result.update(oembed_data)
            result["status"] = "verified"
        else:
            result["status"] = "error"
            result["error"] = oembed_data.get("message", "Unknown error") if oembed_data else "Failed to fetch"

    elif platform == "linkedin":
        print(f"  Processing LinkedIn post: {url}")
        linkedin_data = process_linkedin_post(url)
        result.update(linkedin_data)
        result["status"] = "verified"

    else:
        print(f"  ⚠️  Unknown platform for URL: {url}")
        result["status"] = "error"
        result["error"] = f"Unknown platform. URL must be from x.com/twitter.com or linkedin.com"

    return result


def main():
    """Main entry point: process all social posts and write feed.json."""
    print("=" * 60)
    print("Social Post Processor")
    print("=" * 60)

    # Load inputs
    posts = load_social_posts()
    existing_feed = load_existing_feed()
    archive = load_archive()

    if not posts:
        print("\nNo posts found in social_posts.json.")
        print("Add posts in this format:")
        print(json.dumps([
            {"url": "https://x.com/AtharvPorwal0/status/TWEET_ID", "added_on": "2026-08-19"},
            {"url": "https://www.linkedin.com/posts/atharv-porwal-549526283_...", "added_on": "2026-08-19"},
        ], indent=2))

        # Still write an empty feed so the website doesn't break
        output = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_posts": 0,
            "posts": [],
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Empty feed written to {OUTPUT_FILE}")
        return

    # Build set of already-processed URLs to avoid re-fetching
    already_processed = {
        p.get("url"): p
        for p in existing_feed.get("posts", [])
        if p.get("status") == "verified"
    }

    # Process each post
    processed_posts = []
    new_count = 0
    cached_count = 0
    error_count = 0

    print(f"\nProcessing {len(posts)} posts...")
    for i, post in enumerate(posts, 1):
        url = normalize_url(post.get("url", ""))
        print(f"\n[{i}/{len(posts)}] {url[:80]}...")

        # Reuse cached data if already successfully processed
        if url in already_processed:
            print(f"  ↩️  Already processed (using cached data)")
            processed_posts.append(already_processed[url])
            cached_count += 1
            continue

        # Process new post
        result = process_post(post)
        processed_posts.append(result)

        if result.get("status") == "verified":
            new_count += 1
        else:
            error_count += 1

    # Sort by added_on date (newest first)
    processed_posts.sort(key=lambda p: p.get("added_on", ""), reverse=True)

    # Build output
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "github_username": "AtharvPorwal",
        "x_username": "AtharvPorwal0",
        "linkedin_url": "https://www.linkedin.com/in/atharv-porwal-549526283/",
        "total_posts": len(processed_posts),
        "verified_count": sum(1 for p in processed_posts if p.get("status") == "verified"),
        "error_count": sum(1 for p in processed_posts if p.get("status") == "error"),
        "posts": processed_posts,
    }

    # Write feed.json
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Update archive (append new posts, deduplicate by URL)
    archive_urls = {p.get("url") for p in archive}
    for post in processed_posts:
        if post.get("url") not in archive_urls and post.get("status") == "verified":
            archive.append(post)
            archive_urls.add(post.get("url"))

    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"✅ Feed updated: {OUTPUT_FILE}")
    print(f"   Total posts:  {len(processed_posts)}")
    print(f"   New:          {new_count}")
    print(f"   Cached:       {cached_count}")
    print(f"   Errors:       {error_count}")
    print(f"   Archive size: {len(archive)}")
    print(f"{'=' * 60}")

    # Exit with error code if there are processing errors
    if error_count > 0:
        print(f"\n⚠️  {error_count} post(s) had errors. Check the output above.")
        # Don't exit with error code — partial success is fine


if __name__ == "__main__":
    main()

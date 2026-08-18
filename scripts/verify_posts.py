"""
verify_posts.py — Automated verification that social posts are live on the portfolio.

Runs after each deployment (triggered by verify.yml GitHub Action).
Checks:
  1. feed.json is accessible on the live site
  2. Each post URL is present in the deployed HTML
  3. Original post URLs are still accessible (not deleted / 404)
  4. Data isn't stale (updated within 48 hours)

Usage:
    python scripts/verify_posts.py [SITE_URL]

    SITE_URL defaults to the SITE_URL environment variable, or
    falls back to checking local data files.

Exit codes:
    0 — All checks passed
    1 — One or more checks failed
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# === Configuration ===
LOCAL_FEED_FILE = Path(__file__).resolve().parent.parent / "data" / "feed.json"
LOCAL_SOCIAL_FILE = Path(__file__).resolve().parent.parent / "data" / "social_posts.json"
STALENESS_THRESHOLD_HOURS = 48


class VerificationReport:
    """Tracks verification results and generates a report."""

    def __init__(self):
        self.checks: list[dict] = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def add_pass(self, category: str, description: str, detail: str = ""):
        self.checks.append({
            "status": "PASS", "category": category,
            "description": description, "detail": detail,
        })
        self.passed += 1

    def add_fail(self, category: str, description: str, detail: str = ""):
        self.checks.append({
            "status": "FAIL", "category": category,
            "description": description, "detail": detail,
        })
        self.failed += 1

    def add_warning(self, category: str, description: str, detail: str = ""):
        self.checks.append({
            "status": "WARN", "category": category,
            "description": description, "detail": detail,
        })
        self.warnings += 1

    def print_report(self):
        print("\n" + "=" * 70)
        print("PORTFOLIO VERIFICATION REPORT")
        print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        print("=" * 70)

        for check in self.checks:
            icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}[check["status"]]
            print(f"\n{icon} [{check['status']}] {check['category']}: {check['description']}")
            if check["detail"]:
                print(f"   Detail: {check['detail']}")

        print(f"\n{'=' * 70}")
        print(f"SUMMARY: {self.passed} passed | {self.failed} failed | {self.warnings} warnings")
        print(f"{'=' * 70}")

        if self.failed > 0:
            print(f"\n❌ VERIFICATION FAILED — {self.failed} check(s) did not pass.")
        elif self.warnings > 0:
            print(f"\n⚠️  VERIFICATION PASSED WITH WARNINGS — {self.warnings} warning(s).")
        else:
            print(f"\n✅ ALL CHECKS PASSED.")

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
                "overall": "FAIL" if self.failed > 0 else "PASS",
            },
            "checks": self.checks,
        }, indent=2)


def fetch_url(url: str, timeout: int = 15) -> tuple[int, str]:
    """Fetch a URL and return (status_code, body). Returns (-1, error_msg) on failure."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "PortfolioVerifier/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except urllib.error.URLError as e:
        return -1, str(e.reason)
    except Exception as e:
        return -1, str(e)


def check_url_accessible(url: str) -> tuple[bool, int]:
    """Check if a URL is accessible (returns 200). Returns (is_accessible, status_code)."""
    req = urllib.request.Request(url, method="HEAD", headers={
        "User-Agent": "PortfolioVerifier/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200, response.status
    except urllib.error.HTTPError as e:
        # Some sites block HEAD, try GET
        if e.code == 405:
            status, _ = fetch_url(url, timeout=10)
            return status == 200, status
        return False, e.code
    except Exception:
        return False, -1


def verify_local_data(report: VerificationReport):
    """Verify local data files are valid and consistent."""

    # Check social_posts.json exists
    if LOCAL_SOCIAL_FILE.exists():
        try:
            with open(LOCAL_SOCIAL_FILE, "r", encoding="utf-8") as f:
                social_posts = json.load(f)
            report.add_pass("Local Data", f"social_posts.json is valid JSON ({len(social_posts)} posts)")
        except json.JSONDecodeError as e:
            report.add_fail("Local Data", "social_posts.json has invalid JSON", str(e))
            return
    else:
        report.add_warning("Local Data", "social_posts.json does not exist yet")
        social_posts = []

    # Check feed.json exists and is valid
    if LOCAL_FEED_FILE.exists():
        try:
            with open(LOCAL_FEED_FILE, "r", encoding="utf-8") as f:
                feed = json.load(f)
            report.add_pass("Local Data", f"feed.json is valid JSON ({feed.get('total_posts', 0)} posts)")
        except json.JSONDecodeError as e:
            report.add_fail("Local Data", "feed.json has invalid JSON", str(e))
            return
    else:
        report.add_warning("Local Data", "feed.json does not exist yet (run process_social.py first)")
        return

    # Check staleness
    last_updated = feed.get("last_updated")
    if last_updated:
        try:
            updated_dt = datetime.fromisoformat(last_updated)
            age = datetime.now(timezone.utc) - updated_dt
            if age > timedelta(hours=STALENESS_THRESHOLD_HOURS):
                report.add_warning(
                    "Staleness",
                    f"feed.json is {age.total_seconds() / 3600:.1f} hours old",
                    f"Last updated: {last_updated}. Threshold: {STALENESS_THRESHOLD_HOURS}h.",
                )
            else:
                report.add_pass(
                    "Staleness",
                    f"feed.json is fresh ({age.total_seconds() / 3600:.1f} hours old)",
                )
        except ValueError:
            report.add_warning("Staleness", "Could not parse last_updated timestamp")

    # Check data consistency: all social_posts.json URLs should be in feed.json
    feed_urls = {p.get("url") for p in feed.get("posts", [])}
    for post in social_posts:
        url = post.get("url", "").strip().rstrip("/")
        # Normalize twitter.com → x.com for comparison
        url_normalized = url.replace("twitter.com/", "x.com/")
        if url_normalized in feed_urls or url in feed_urls:
            report.add_pass("Data Consistency", f"Post URL in feed", url[:80])
        else:
            report.add_fail("Data Consistency", f"Post URL missing from feed.json", url[:80])

    # Check each post's status in feed.json
    for post in feed.get("posts", []):
        url = post.get("url", "")[:80]
        status = post.get("status")
        if status == "verified":
            report.add_pass("Post Status", f"{post.get('platform', '?')} post is verified", url)
        elif status == "error":
            report.add_fail(
                "Post Status",
                f"{post.get('platform', '?')} post has error",
                f"{url} — {post.get('error', 'Unknown error')}",
            )


def verify_post_urls_accessible(report: VerificationReport):
    """Check that the original social media post URLs are still live (not deleted)."""
    if not LOCAL_FEED_FILE.exists():
        return

    with open(LOCAL_FEED_FILE, "r", encoding="utf-8") as f:
        feed = json.load(f)

    posts = feed.get("posts", [])
    if not posts:
        report.add_warning("URL Accessibility", "No posts to check")
        return

    print("\nChecking if original post URLs are still accessible...")
    for post in posts:
        url = post.get("url", "")
        platform = post.get("platform", "unknown")

        if not url:
            continue

        is_accessible, status_code = check_url_accessible(url)

        if is_accessible:
            report.add_pass("URL Accessibility", f"{platform} post is live (HTTP {status_code})", url[:80])
        elif status_code == 404:
            report.add_fail(
                "URL Accessibility",
                f"{platform} post returns 404 — may be deleted",
                url[:80],
            )
        elif status_code in (401, 403):
            # Some platforms return 403 for public content when accessed via HEAD/automated requests
            report.add_warning(
                "URL Accessibility",
                f"{platform} post returned {status_code} (may still be live — platform blocks bots)",
                url[:80],
            )
        else:
            report.add_warning(
                "URL Accessibility",
                f"{platform} post returned HTTP {status_code}",
                url[:80],
            )


def verify_live_site(site_url: str, report: VerificationReport):
    """Verify that posts appear on the live deployed portfolio site."""
    print(f"\nChecking live site: {site_url}")

    # Fetch the live site HTML
    status, body = fetch_url(site_url)
    if status != 200:
        report.add_fail("Live Site", f"Could not reach {site_url}", f"HTTP {status}")
        return

    report.add_pass("Live Site", f"Site is accessible (HTTP 200)", site_url)

    # Check if feed.json is accessible on the live site
    feed_url = site_url.rstrip("/") + "/data/feed.json"
    status, feed_body = fetch_url(feed_url)
    if status == 200:
        try:
            live_feed = json.loads(feed_body)
            report.add_pass("Live Site", f"feed.json is accessible on live site ({live_feed.get('total_posts', 0)} posts)")

            # Compare local vs live feed
            if LOCAL_FEED_FILE.exists():
                with open(LOCAL_FEED_FILE, "r", encoding="utf-8") as f:
                    local_feed = json.load(f)

                local_updated = local_feed.get("last_updated", "")
                live_updated = live_feed.get("last_updated", "")

                if local_updated == live_updated:
                    report.add_pass("Data Sync", "Live feed matches local feed (same timestamp)")
                else:
                    report.add_warning(
                        "Data Sync",
                        "Live feed timestamp differs from local",
                        f"Local: {local_updated} | Live: {live_updated}",
                    )
        except json.JSONDecodeError:
            report.add_fail("Live Site", "feed.json on live site is not valid JSON")
    else:
        report.add_warning(
            "Live Site",
            f"feed.json not found on live site (HTTP {status})",
            "This is expected if the site hasn't been deployed yet.",
        )

    # Check that post URLs appear in the page HTML
    if LOCAL_FEED_FILE.exists():
        with open(LOCAL_FEED_FILE, "r", encoding="utf-8") as f:
            feed = json.load(f)

        for post in feed.get("posts", []):
            url = post.get("url", "")
            platform = post.get("platform", "unknown")

            if not url:
                continue

            if url in body:
                report.add_pass("Live Rendering", f"{platform} post URL found in page HTML", url[:80])
            else:
                report.add_fail("Live Rendering", f"{platform} post URL NOT found in page HTML", url[:80])


def main():
    """Main entry point: run all verification checks."""
    # Determine site URL
    site_url = None
    if len(sys.argv) > 1:
        site_url = sys.argv[1]
    else:
        site_url = os.environ.get("SITE_URL")

    report = VerificationReport()

    # Phase 1: Verify local data files
    print("Phase 1: Verifying local data files...")
    verify_local_data(report)

    # Phase 2: Check original post URLs are still accessible
    print("\nPhase 2: Checking original post URLs...")
    verify_post_urls_accessible(report)

    # Phase 3: Verify live site (if URL provided)
    if site_url:
        print(f"\nPhase 3: Verifying live site ({site_url})...")
        verify_live_site(site_url, report)
    else:
        report.add_warning(
            "Live Site",
            "No SITE_URL provided — skipping live site verification",
            "Set SITE_URL env var or pass as argument to enable live checks.",
        )

    # Print report
    report.print_report()

    # Save report to file
    report_file = Path(__file__).resolve().parent.parent / "data" / "verification_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report.to_json())
    print(f"\nReport saved to: {report_file}")

    # Exit with appropriate code
    sys.exit(1 if report.failed > 0 else 0)


if __name__ == "__main__":
    main()

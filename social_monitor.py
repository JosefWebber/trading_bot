"""
Social Media Monitor
--------------------
Polls multiple sources for new posts from:
  - Donald Trump (Truth Social + RSS fallback)
  - Elon Musk (multiple Nitter instances)
  - Michael Saylor (multiple Nitter instances)
  - Cathie Wood (multiple Nitter instances)
"""

import re
import logging
import feedparser
import requests
from typing import List, Dict, Set

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
#  Nitter instances — tries each until one works
# ----------------------------------------------------------------
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.1d4.us",
    "https://xcancel.com",
    "https://nitter.space",
    "https://lightbrd.com",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Twitter/X accounts to monitor via Nitter
TWITTER_ACCOUNTS: Dict[str, str] = {
    "elonmusk":    "Elon Musk",
    "saylor":      "Michael Saylor",
    "cathiedwood": "Cathie Wood",
}

# Truth Social — multiple endpoint formats to try
TRUMP_ACCOUNT_ID = "107780257626128497"

TRUTH_SOCIAL_URLS = [
    f"https://truthsocial.com/api/v1/accounts/{TRUMP_ACCOUNT_ID}/statuses?limit=10",
    f"https://truthsocial.com/api/v2/accounts/{TRUMP_ACCOUNT_ID}/statuses?limit=10",
]

# RSS fallback for Trump (various aggregators track his posts)
TRUMP_RSS_FEEDS = [
    "https://rss.app/feeds/trump-truth-social.xml",
    "https://feeds.feedburner.com/realdonaldtrump",
]


def _strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


class SocialMonitor:
    def __init__(self):
        self._seen: Dict[str, Set[str]] = {}
        self._working_nitter: str | None = None

    # ----------------------------------------------------------------
    #  Nitter RSS
    # ----------------------------------------------------------------
    def _fetch_nitter(self, username: str) -> List[dict]:
        instances = (
            [self._working_nitter] + [i for i in NITTER_INSTANCES if i != self._working_nitter]
            if self._working_nitter else NITTER_INSTANCES
        )
        for instance in instances:
            try:
                url  = f"{instance}/{username}/rss"
                feed = feedparser.parse(url, request_headers=HEADERS)
                if feed.entries and len(feed.entries) > 0:
                    self._working_nitter = instance
                    logger.info(f"  Nitter working: {instance}")
                    return feed.entries[:10]
            except Exception:
                continue
        return []

    def _get_twitter_posts(self, username: str, display_name: str) -> List[dict]:
        entries = self._fetch_nitter(username)
        seen    = self._seen.setdefault(username, set())
        posts   = []

        for entry in entries:
            post_id = entry.get("id") or entry.get("link", "")
            if post_id in seen:
                continue
            raw  = entry.get("summary") or entry.get("title", "")
            text = _strip_html(raw)
            posts.append({
                "id":       post_id,
                "author":   display_name,
                "text":     text,
                "platform": "twitter",
            })
            seen.add(post_id)

        return posts

    # ----------------------------------------------------------------
    #  Truth Social (Trump)
    # ----------------------------------------------------------------
    def _get_trump_posts(self) -> List[dict]:
        seen  = self._seen.setdefault("trump", set())
        posts = []

        # Try Truth Social API endpoints
        for url in TRUTH_SOCIAL_URLS:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    for status in resp.json():
                        post_id = str(status.get("id", ""))
                        if post_id in seen:
                            continue
                        text = _strip_html(status.get("content", ""))
                        if text:
                            posts.append({
                                "id":       post_id,
                                "author":   "Donald Trump",
                                "text":     text,
                                "platform": "truth_social",
                            })
                            seen.add(post_id)
                    if posts:
                        return posts
            except Exception as e:
                logger.debug(f"Truth Social API attempt failed: {e}")
                continue

        # Fallback: try RSS feeds
        for feed_url in TRUMP_RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url, request_headers=HEADERS)
                if feed.entries:
                    for entry in feed.entries[:10]:
                        post_id = entry.get("id") or entry.get("link", "")
                        if post_id in seen:
                            continue
                        text = _strip_html(
                            entry.get("summary") or entry.get("title", "")
                        )
                        if text:
                            posts.append({
                                "id":       post_id,
                                "author":   "Donald Trump",
                                "text":     text,
                                "platform": "rss",
                            })
                            seen.add(post_id)
                    if posts:
                        return posts
            except Exception as e:
                logger.debug(f"Trump RSS fallback failed: {e}")
                continue

        logger.warning("Could not fetch Trump posts from any source")
        return []

    # ----------------------------------------------------------------
    #  Public — call this every CHECK_INTERVAL_SECONDS
    # ----------------------------------------------------------------
    def get_all_new_posts(self) -> List[dict]:
        all_posts: List[dict] = []

        for username, display_name in TWITTER_ACCOUNTS.items():
            try:
                posts = self._get_twitter_posts(username, display_name)
                all_posts.extend(posts)
                if posts:
                    logger.info(f"  {display_name}: {len(posts)} new post(s)")
            except Exception as e:
                logger.error(f"Error fetching {display_name}: {e}")

        try:
            trump_posts = self._get_trump_posts()
            all_posts.extend(trump_posts)
            if trump_posts:
                logger.info(f"  Donald Trump: {len(trump_posts)} new post(s)")
        except Exception as e:
            logger.error(f"Error fetching Trump posts: {e}")

        return all_posts

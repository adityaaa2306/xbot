"""Creator ingestion using public X mirrors, with embed helpers retained for debugging/tests."""

import asyncio
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import List, Optional

import config
import httpx
from ingestion.models import CreatorTarget, SignalTweet
from logger import logger

try:
    from playwright.async_api import Browser, BrowserContext, Frame, Page, async_playwright
except ImportError:  # pragma: no cover - exercised in environments without playwright
    Browser = BrowserContext = Frame = Page = None
    async_playwright = None


class PlaywrightXScraper:
    """Scrape public creator timelines via a text mirror, with embed helpers as fallback tools."""

    READER_BASE_URL = "https://r.jina.ai/http://https://x.com"
    STATUS_LINE_RE = re.compile(
        r"^\[(?P<date>[A-Za-z]{3,9} \d{1,2}, \d{4})\]\(https://x\.com/(?P<author>[^/]+)/status/(?P<tweet_id>\d+)\)$"
    )
    PHOTO_STATUS_LINE_RE = re.compile(
        r"https://x\.com/(?P<author>[^/]+)/status/(?P<tweet_id>\d+)/photo/\d+"
    )
    METRIC_VALUE_RE = re.compile(r"^[0-9][0-9.,]*[KMB]?$", re.IGNORECASE)
    ANALYTICS_LINK_RE = re.compile(r"^\[[0-9][0-9.,]*[KMB]?\]\(https://x\.com/.+/status/\d+/analytics\)$", re.IGNORECASE)

    def __init__(
        self,
        *,
        headless: bool = config.SIGNAL_HEADLESS,
        page_delay_range: tuple[float, float] = (
            config.SIGNAL_PAGE_DELAY_MIN_SECS,
            config.SIGNAL_PAGE_DELAY_MAX_SECS,
        ),
        scroll_delay_range: tuple[float, float] = (
            config.SIGNAL_SCROLL_DELAY_MIN_SECS,
            config.SIGNAL_SCROLL_DELAY_MAX_SECS,
        ),
        scrolls_per_page: int = config.SIGNAL_SCROLLS_PER_PAGE,
    ):
        self.headless = headless
        self.page_delay_range = page_delay_range
        self.scroll_delay_range = scroll_delay_range
        self.scrolls_per_page = scrolls_per_page
        self.embed_html_path = Path(__file__).parent / "embed_profile.html"

    async def scrape_creators(self, creators: List[CreatorTarget], max_tweets: int) -> List[SignalTweet]:
        """Scrape public timelines from creator list using a no-login reader mirror."""
        return await self._scrape_creators_via_reader(creators, max_tweets=max_tweets)

    async def scrape_search_queries(self, queries: List[str], max_tweets: int) -> List[SignalTweet]:
        """Search is temporarily disabled for Phase 1 (creator-only ingestion)."""
        logger.info("SIGNAL_SEARCH_DISABLED", phase="INGESTION", data={"reason": "phase_1_creator_only"})
        return []

    async def _scrape_creators_via_reader(self, creators: List[CreatorTarget], max_tweets: int) -> List[SignalTweet]:
        """Scrape public creator timelines via a text mirror that exposes page content without login."""
        results: List[SignalTweet] = []

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT},
        ) as client:
            for creator in creators:
                if not creator.enabled:
                    continue

                await self._human_pause(*self.page_delay_range)
                try:
                    markdown = await self._fetch_reader_markdown(client, creator.username)
                    extracted = self._parse_reader_profile_markdown(markdown, creator, max_tweets)
                    results.extend(extracted)
                    logger.info(
                        "SIGNAL_CREATOR_SCRAPED",
                        phase="INGESTION",
                        data={
                            "creator": creator.username,
                            "tier": creator.tier,
                            "count": len(extracted),
                            "provider": "reader",
                        },
                    )
                except Exception as exc:
                    logger.warn(
                        "SIGNAL_CREATOR_FAILED",
                        phase="INGESTION",
                        data={
                            "creator": creator.username,
                            "provider": "reader",
                            "error": str(exc),
                        },
                    )

        return results[: config.SIGNAL_MAX_TWEETS_PER_DAY]

    async def _fetch_reader_markdown(self, client: httpx.AsyncClient, username: str) -> str:
        response = await client.get(f"{self.READER_BASE_URL}/{username}")
        response.raise_for_status()
        return response.text

    def _parse_reader_profile_markdown(
        self,
        markdown: str,
        creator: CreatorTarget,
        limit: int,
    ) -> List[SignalTweet]:
        lines = [line.strip() for line in markdown.splitlines()]
        tweets: List[SignalTweet] = []
        seen_ids: set[str] = set()
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        index = 0

        while index < len(lines) and len(tweets) < limit:
            match = self.STATUS_LINE_RE.match(lines[index])
            if not match:
                index += 1
                continue

            tweet_id = match.group("tweet_id")
            author = match.group("author")
            timestamp = self._normalize_reader_date(match.group("date"), tweet_id=tweet_id)
            url = f"https://x.com/{author}/status/{tweet_id}"

            index += 1
            text_lines: List[str] = []
            metric_values: List[int] = []

            while index < len(lines):
                line = lines[index]
                if self.STATUS_LINE_RE.match(line):
                    break

                if not line:
                    index += 1
                    continue

                if self.ANALYTICS_LINK_RE.match(line):
                    index += 1
                    continue

                if line.startswith("[![Image") or line.startswith("![Image"):
                    index += 1
                    continue

                if self.METRIC_VALUE_RE.match(line):
                    metric_values.append(self._parse_metric_value(line))
                    index += 1
                    continue

                if self._is_reader_scaffold_line(line, creator.username, author):
                    index += 1
                    continue

                if line.startswith("[") and "](" in line:
                    index += 1
                    continue

                text_lines.append(line)
                index += 1

            text = self._normalize_text(" ".join(text_lines))
            if text:
                replies = metric_values[0] if len(metric_values) > 0 else 0
                retweets = metric_values[1] if len(metric_values) > 1 else 0
                likes = metric_values[2] if len(metric_values) > 2 else 0
                tweets.append(
                    SignalTweet(
                        tweet_id=tweet_id,
                        text=text,
                        author=author or creator.username,
                        likes=likes,
                        replies=replies,
                        retweets=retweets,
                        timestamp=timestamp,
                        source="creator",
                        url=url,
                        query=None,
                        scraped_at=now_iso,
                        creator_tier=creator.tier,
                    )
                )
                seen_ids.add(tweet_id)

        if len(tweets) >= limit:
            return tweets[:limit]

        for index, line in enumerate(lines):
            photo_match = self.PHOTO_STATUS_LINE_RE.search(line)
            if not photo_match:
                continue

            tweet_id = photo_match.group("tweet_id")
            author = photo_match.group("author")
            if tweet_id in seen_ids or author.lower() != creator.username.lower():
                continue

            text = self._find_fallback_text_before_photo(lines, index, creator.username, author)
            if not text:
                continue

            tweets.append(
                SignalTweet(
                    tweet_id=tweet_id,
                    text=text,
                    author=author,
                    likes=0,
                    replies=0,
                    retweets=0,
                    timestamp=self._normalize_reader_date(None, tweet_id=tweet_id),
                    source="creator",
                    url=f"https://x.com/{author}/status/{tweet_id}",
                    query=None,
                    scraped_at=now_iso,
                    creator_tier=creator.tier,
                )
            )
            seen_ids.add(tweet_id)
            if len(tweets) >= limit:
                break

        return tweets[:limit]

    async def _scrape_creators_via_embed(self, creators: List[CreatorTarget], max_tweets: int) -> List[SignalTweet]:
        """Scrape public creator timelines using embedded X widget (no login required)."""
        if async_playwright is None:
            raise RuntimeError("playwright is not installed. Add it to requirements and install browsers.")

        results: List[SignalTweet] = []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent=self._random_user_agent(),
                viewport={"width": 1440, "height": 1024},
                locale="en-US",
                timezone_id="UTC",
            )
            
            try:
                for creator in creators:
                    if not creator.enabled:
                        continue
                    
                    await self._human_pause(*self.page_delay_range)
                    page = await context.new_page()
                    
                    try:
                        # Load the local embed HTML file
                        file_url = self.embed_html_path.as_uri()
                        await page.goto(file_url, wait_until="domcontentloaded", timeout=60000)

                        await page.wait_for_function(
                            "() => typeof window.loadTimeline === 'function'",
                            timeout=15000,
                        )

                        # Call JavaScript to load the timeline widget
                        await page.evaluate(
                            "([username, tweetLimit]) => window.loadTimeline(username, tweetLimit)",
                            [creator.username, max_tweets],
                        )

                        # Extract tweets from the rendered embed
                        extracted = await self._extract_tweets_from_embed(page, creator, max_tweets)
                        results.extend(extracted)

                        logger.info(
                            "SIGNAL_CREATOR_SCRAPED",
                            phase="INGESTION",
                            data={
                                "creator": creator.username,
                                "tier": creator.tier,
                                "count": len(extracted),
                            },
                        )
                    except Exception as exc:
                        logger.warn(
                            "SIGNAL_CREATOR_FAILED",
                            phase="INGESTION",
                            data={
                                "creator": creator.username,
                                "error": str(exc),
                            },
                        )
                    finally:
                        await page.close()
            finally:
                await context.close()
                await browser.close()

        return results[: config.SIGNAL_MAX_TWEETS_PER_DAY]

    async def _extract_tweets_from_embed(self, page: Page, creator: CreatorTarget, limit: int) -> List[SignalTweet]:
        """Extract tweets from the rendered X timeline embed."""
        try:
            frame = await self._wait_for_timeline_frame(page)
            if frame is None:
                logger.warn(
                    "SIGNAL_TIMELINE_FRAME_NOT_FOUND",
                    phase="INGESTION",
                    data={"creator": creator.username},
                )
                return []

            return await self._extract_tweets_from_container(
                frame,
                source="creator",
                query=None,
                limit=limit,
                forced_author=creator.username,
                forced_tier=creator.tier,
            )
        except Exception as exc:
            logger.warn("SIGNAL_EMBED_EXTRACT_FAILED", phase="INGESTION", data={"error": str(exc)})
            return []

    async def _human_pause(self, low: float, high: float) -> None:
        await asyncio.sleep(random.uniform(low, high))

    def _normalize_text(self, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned

    def _normalize_reader_date(self, value: Optional[str], *, tweet_id: Optional[str] = None) -> str:
        if value:
            for date_format in ("%b %d, %Y", "%B %d, %Y"):
                try:
                    parsed = datetime.strptime(value, date_format)
                    return parsed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                except ValueError:
                    continue
        if tweet_id:
            inferred = self._timestamp_from_tweet_id(tweet_id)
            if inferred:
                return inferred
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _is_reader_scaffold_line(self, line: str, creator_username: str, author_username: str) -> bool:
        lower = line.lower()
        if lower in {"pinned", "follow", "see new posts", "pcf_label_none", "·", "quote", "repost"}:
            return True
        if lower.startswith("click to follow "):
            return True
        if lower in {creator_username.lower(), f"@{creator_username.lower()}"}:
            return True
        if lower in {author_username.lower(), f"@{author_username.lower()}"}:
            return True
        return False

    def _parse_metric_value(self, raw: str) -> int:
        cleaned = raw.replace(",", "").strip().upper()
        match = re.match(r"([0-9]*\.?[0-9]+)([KMB])?", cleaned)
        if not match:
            return 0
        value = float(match.group(1))
        unit = match.group(2)
        if unit == "K":
            value *= 1_000
        elif unit == "M":
            value *= 1_000_000
        elif unit == "B":
            value *= 1_000_000_000
        return int(round(value))

    def _find_fallback_text_before_photo(
        self,
        lines: List[str],
        photo_index: int,
        creator_username: str,
        author_username: str,
    ) -> str:
        for index in range(photo_index - 1, max(-1, photo_index - 8), -1):
            line = lines[index].strip()
            if not line:
                continue
            if self.STATUS_LINE_RE.match(line) or self.PHOTO_STATUS_LINE_RE.match(line):
                break
            if self.ANALYTICS_LINK_RE.match(line):
                continue
            if line.startswith("[![Image") or line.startswith("![Image"):
                continue
            if line.startswith("[") and "](" in line:
                continue
            if self.METRIC_VALUE_RE.match(line):
                continue
            if self._is_reader_scaffold_line(line, creator_username, author_username):
                continue
            return self._normalize_text(line)
        return ""

    def _timestamp_from_tweet_id(self, tweet_id: str) -> Optional[str]:
        try:
            snowflake = int(tweet_id)
        except ValueError:
            return None

        twitter_epoch_ms = 1288834974657
        timestamp_ms = (snowflake >> 22) + twitter_epoch_ms
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return dt.isoformat().replace("+00:00", "Z")

    def _random_user_agent(self) -> str:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        ]
        return random.choice(user_agents)

    async def _wait_for_timeline_frame(self, page: Page, timeout_ms: int = 20000) -> Optional[Frame]:
        """Wait for the embedded timeline iframe and return the frame once tweets are present."""
        await page.wait_for_selector("iframe", state="attached", timeout=timeout_ms)

        preferred_hosts = ("platform.x.com", "platform.twitter.com", "syndication.twitter.com")
        deadline = monotonic() + (timeout_ms / 1000)
        fallback_frame: Optional[Frame] = None

        while monotonic() < deadline:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue

                frame_url = frame.url or ""
                if frame_url and any(host in frame_url for host in preferred_hosts):
                    fallback_frame = frame

                try:
                    article_count = await frame.locator("article").count()
                    if article_count > 0:
                        return frame
                except Exception:
                    continue

            await page.wait_for_timeout(250)

        return fallback_frame

    async def _extract_tweets_from_container(
        self,
        container: Page | Frame,
        *,
        source: str,
        query: Optional[str],
        limit: int,
        forced_author: Optional[str] = None,
        forced_tier: Optional[str] = None,
    ) -> List[SignalTweet]:
        payload = await container.locator("article").evaluate_all(
            """
            (articles, meta) => {
              const parseMetric = (raw) => {
                if (!raw) return 0;
                const cleaned = raw.replace(/,/g, '').trim().toUpperCase();
                const match = cleaned.match(/([0-9]*\\.?[0-9]+)([KMB])?/);
                if (!match) return 0;
                const value = parseFloat(match[1]);
                const unit = match[2];
                if (unit === 'K') return Math.round(value * 1000);
                if (unit === 'M') return Math.round(value * 1000000);
                if (unit === 'B') return Math.round(value * 1000000000);
                return Math.round(value);
              };

              return articles.map((article) => {
                const link = Array.from(article.querySelectorAll("a[href*='/status/']"))
                  .map((node) => node.getAttribute("href"))
                  .find((href) => href && href.includes("/status/"));
                if (!link) return null;

                const tweetTextContainer = article.querySelector("[data-testid='tweetText']");
                const text = tweetTextContainer ? tweetTextContainer.innerText.trim() : "";
                if (!text) return null;

                if (article.innerText.includes("Replying to")) return null;

                const timeNode = article.querySelector("time");
                const timestamp = timeNode ? timeNode.getAttribute("datetime") : null;
                const authorFromLink = link.split("/status/")[0].split("/").filter(Boolean).pop();
                const author = meta.forcedAuthor || authorFromLink || "";

                return {
                  tweet_id: link.split("/status/").pop().split(/[/?]/)[0],
                  text,
                  author,
                  likes: parseMetric(article.querySelector("[data-testid='like']")?.innerText || "0"),
                  replies: parseMetric(article.querySelector("[data-testid='reply']")?.innerText || "0"),
                  retweets: parseMetric(article.querySelector("[data-testid='retweet']")?.innerText || "0"),
                  timestamp,
                  source: meta.source,
                  url: link.startsWith("http") ? link : `https://x.com${link}`,
                  query: meta.query || null
                };
              }).filter(Boolean);
            }
            """,
            {"source": source, "query": query, "forcedAuthor": forced_author},
        )

        tweets: List[SignalTweet] = []
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for item in payload[:limit]:
            if not item.get("tweet_id") or not item.get("timestamp"):
                continue
            tweets.append(
                SignalTweet(
                    tweet_id=str(item["tweet_id"]),
                    text=self._normalize_text(str(item["text"])),
                    author=str(item.get("author") or forced_author or ""),
                    likes=int(item.get("likes") or 0),
                    replies=int(item.get("replies") or 0),
                    retweets=int(item.get("retweets") or 0),
                    timestamp=str(item["timestamp"]),
                    source=source,
                    url=str(item["url"]),
                    query=query,
                    scraped_at=now_iso,
                    creator_tier=forced_tier,
                )
            )
        return tweets

    # Legacy method for backwards-compatibility with tests
    async def extract_tweets_from_page(
        self,
        page: Page,
        *,
        source: str,
        query: Optional[str],
        limit: int,
        forced_author: Optional[str] = None,
    ) -> List[SignalTweet]:
        """Legacy extraction from article elements (for fixture-based tests)."""
        return await self._extract_tweets_from_container(
            page,
            source=source,
            query=query,
            limit=limit,
            forced_author=forced_author,
        )

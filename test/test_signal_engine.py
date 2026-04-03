import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from filtering.signal_filter import SignalFilter
from generator import build_generation_prompt, load_context
from ingestion.models import CreatorTarget, SignalTweet
from ingestion.targets import build_run_targets
from ingestion.x_scraper import PlaywrightXScraper, async_playwright
from research.brief_engine import ResearchBriefEngine
from signal_engine import SignalEngine


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, *args, **kwargs):
        return self._responses.pop(0)


class FakeScraper:
    async def scrape_creators(self, creators, max_tweets):
        return [
            SignalTweet(
                tweet_id="1",
                text="Leverage compounds faster than effort when the asset keeps working after you stop.",
                author="naval",
                likes=500,
                replies=30,
                retweets=90,
                timestamp="2026-04-02T06:00:00Z",
                source="creator",
                url="https://x.com/naval/status/1",
                scraped_at="2026-04-02T06:30:00Z",
            )
        ]

    async def scrape_search_queries(self, queries, max_tweets):
        return [
            SignalTweet(
                tweet_id="2",
                text="Most people build harder. Smart people build systems that reduce force over time.",
                author="thedankoe",
                likes=420,
                replies=16,
                retweets=55,
                timestamp="2026-04-02T05:30:00Z",
                source="search",
                url="https://x.com/thedankoe/status/2",
                query="leverage",
                scraped_at="2026-04-02T06:31:00Z",
            )
        ]


class FakeBriefEngine:
    async def build_brief(self, signals):
        analyses = [
            {
                "tweet_id": signal.tweet_id,
                "core_idea": signal.text.split(".")[0],
                "hook_type": "contrarian",
                "emotional_trigger": "ambition",
                "writing_style": "short punchy",
                "why_it_worked": "Clear contrast and sharp status signal.",
            }
            for signal in signals
        ]
        brief = {
            "generated_at": "2026-04-02T06:35:00Z",
            "top_insights": ["Leverage scales where effort saturates."],
            "hook_patterns": ["contrarian opener"],
            "angles": ["systems over effort"],
            "emotional_drivers": ["ambition"],
            "emerging_narrative": "Ownership beats output.",
            "viral_examples": [signal.to_dict() for signal in signals],
            "winning_patterns": ["contrarian opener"],
            "failed_patterns": [],
            "avoid_recent_hooks": [],
            "avoid_recent_ideas": [],
            "source_summary": {"creator": 1, "search": 1},
        }
        return analyses, brief


class SignalTargetsTest(unittest.TestCase):
    def test_build_run_targets_uses_core_and_rotating_batches(self):
        fixed_now = __import__("datetime").datetime(2026, 4, 2, 9, 0, 0)
        targets = build_run_targets(fixed_now)
        self.assertGreaterEqual(len(targets["creators"]), 8)
        self.assertLessEqual(len(targets["search_queries"]), config.SIGNAL_SEARCH_QUERIES_PER_RUN)


class SignalFilterTest(unittest.TestCase):
    def test_filter_and_rank_removes_promo_and_scores_remaining(self):
        engine = SignalFilter()
        signals = [
            SignalTweet(
                tweet_id="a",
                text="Leverage compounds faster than effort when the asset keeps working after you stop.",
                author="naval",
                likes=500,
                replies=30,
                retweets=90,
                timestamp="2026-04-02T06:00:00Z",
                source="creator",
                url="https://x.com/naval/status/a",
            ),
            SignalTweet(
                tweet_id="b",
                text="Join my newsletter https://example.com for the full framework and templates.",
                author="spam",
                likes=900,
                replies=50,
                retweets=10,
                timestamp="2026-04-02T06:00:00Z",
                source="search",
                url="https://x.com/spam/status/b",
            ),
        ]
        ranked = engine.filter_and_rank(signals)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].tweet_id, "a")
        self.assertGreater(ranked[0].rank_score, 0)


class ResearchBriefTest(unittest.IsolatedAsyncioTestCase):
    async def test_brief_engine_builds_structured_brief(self):
        client = FakeClient(
            [
                json.dumps(
                    [
                        {
                            "tweet_id": "1",
                            "core_idea": "Leverage turns output into assets.",
                            "hook_type": "contrarian",
                            "emotional_trigger": "ambition",
                            "writing_style": "short punchy",
                            "why_it_worked": "It compressed a big belief into one sentence.",
                        }
                    ]
                ),
                json.dumps(
                    {
                        "recurring_ideas": ["Leverage over labor"],
                        "hook_patterns": ["contrarian"],
                        "emotional_drivers": ["ambition"],
                        "emerging_narrative": "Freedom comes from assets.",
                        "angles": ["systems over effort"],
                    }
                ),
                json.dumps(["Leverage compounds where labor stalls."]),
            ]
        )
        engine = ResearchBriefEngine(client=client)
        signals = [
            SignalTweet(
                tweet_id="1",
                text="Leverage compounds faster than labor when the asset keeps running.",
                author="naval",
                likes=500,
                replies=30,
                retweets=90,
                timestamp="2026-04-02T06:00:00Z",
                source="creator",
                url="https://x.com/naval/status/1",
            )
        ]
        analyses, brief = await engine.build_brief(signals)
        self.assertEqual(len(analyses), 1)
        self.assertIn("top_insights", brief)
        self.assertEqual(brief["top_insights"][0], "Leverage compounds where labor stalls.")


class GeneratorIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_generation_prompt_uses_latest_research_brief(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "research_brief.json"
            brief_path.write_text(
                json.dumps(
                    {
                        "top_insights": ["Leverage compounds where labor stalls."],
                        "hook_patterns": ["contrarian opener"],
                        "angles": ["systems over effort"],
                        "emotional_drivers": ["ambition"],
                        "emerging_narrative": "Freedom comes from assets."
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(config, "LATEST_RESEARCH_BRIEF_FILE", str(brief_path)):
                context = await load_context()
                system_prompt, user_prompt = build_generation_prompt(
                    "brutal_truth",
                    "wealth_leverage",
                    "provocative",
                    1,
                    False,
                    context,
                )

        self.assertIn("Leverage compounds where labor stalls.", system_prompt)
        self.assertIn("systems over effort", user_prompt)


class SignalEngineTest(unittest.IsolatedAsyncioTestCase):
    async def test_signal_engine_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with mock.patch.object(config, "SIGNAL_RAW_LOG_FILE", str(base / "signal_raw.jsonl")), \
                mock.patch.object(config, "SIGNAL_FILTERED_LOG_FILE", str(base / "signal_filtered.jsonl")), \
                mock.patch.object(config, "SIGNAL_ANALYSIS_LOG_FILE", str(base / "signal_analyses.jsonl")), \
                mock.patch.object(config, "RESEARCH_BRIEF_LOG_FILE", str(base / "research_briefs.jsonl")), \
                mock.patch.object(config, "LATEST_RESEARCH_BRIEF_FILE", str(base / "research_brief.json")), \
                mock.patch("signal_engine.build_run_targets", return_value={
                    "creators": [{"display_name": "Naval Ravikant", "username": "naval", "tier": "core", "enabled": True}],
                    "search_queries": ["leverage"],
                    "run_slot": 0,
                }):
                engine = SignalEngine(
                    scraper=FakeScraper(),
                    brief_engine=FakeBriefEngine(),
                )
                result = await engine.run()

            self.assertEqual(result["ranked_count"], 2)
            self.assertEqual(result["filtered_count"], 2)
            self.assertEqual(result["analyses_count"], 2)
            self.assertTrue((base / "signal_raw.jsonl").exists())
            self.assertTrue((base / "signal_filtered.jsonl").exists())
            self.assertTrue((base / "research_brief.json").exists())


class ReaderScraperParsingTest(unittest.TestCase):
    def test_parse_reader_profile_markdown_extracts_tweets_and_metrics(self):
        scraper = PlaywrightXScraper(headless=True, page_delay_range=(0, 0), scroll_delay_range=(0, 0), scrolls_per_page=0)
        creator = CreatorTarget(display_name="Naval Ravikant", username="naval", tier="core", enabled=True)
        markdown = """
# Naval (@naval) / X

# Naval’s posts

[Naval](https://x.com/naval)

[@naval](https://x.com/naval)

·

[Feb 1, 2025](https://x.com/naval/status/1885783497601892782)

[![Image 10](https://abs.twimg.com/responsive-web/client-web/parody-mask.92274f0a.svg) PCF_LABEL_NONE](https://help.x.com/rules-and-policies/authenticity)

Nobody who's actually good at making money needs to sell you a course on it.

1.9K

15K

109K

[5.1M](https://x.com/naval/status/1885783497601892782/analytics)

[Jun 5, 2025](https://x.com/naval/status/1930721134368129164)

Leverage is a force multiplier for judgment, not a substitute for it.

820

6.4K

42K

[18M](https://x.com/naval/status/1930721134368129164/analytics)
"""

        tweets = scraper._parse_reader_profile_markdown(markdown, creator, limit=10)

        self.assertEqual(len(tweets), 2)
        self.assertEqual(tweets[0].tweet_id, "1885783497601892782")
        self.assertIn("sell you a course", tweets[0].text)
        self.assertEqual(tweets[0].replies, 1900)
        self.assertEqual(tweets[0].retweets, 15000)
        self.assertEqual(tweets[0].likes, 109000)
        self.assertEqual(tweets[0].creator_tier, "core")

    def test_parse_reader_profile_markdown_falls_back_to_photo_links(self):
        scraper = PlaywrightXScraper(headless=True, page_delay_range=(0, 0), scroll_delay_range=(0, 0), scrolls_per_page=0)
        creator = CreatorTarget(display_name="Dickie Bush", username="dickiebush", tier="core", enabled=True)
        markdown = """
## Dickie Bush's posts

Pinned

If you use it right, Twitter is the most powerful platform in the world.

[![Image 4: Image](https://pbs.twimg.com/media/F6892n_X0AAj0yf?format=png&name=small)](https://x.com/dickiebush/status/1706651022423196152/photo/1)
"""

        tweets = scraper._parse_reader_profile_markdown(markdown, creator, limit=10)

        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0].tweet_id, "1706651022423196152")
        self.assertIn("most powerful platform", tweets[0].text)
        self.assertEqual(tweets[0].likes, 0)


@unittest.skipIf(async_playwright is None, "playwright not installed")
class PlaywrightScraperTest(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_tweets_from_fixture_page(self):
        fixture_path = Path(__file__).parent / "fixtures" / "sample_x_feed.html"
        scraper = PlaywrightXScraper(headless=True, page_delay_range=(0, 0), scroll_delay_range=(0, 0), scrolls_per_page=0)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(fixture_path.as_uri())
            tweets = await scraper.extract_tweets_from_page(
                page,
                source="creator",
                query=None,
                limit=10,
                forced_author="naval",
            )
            await context.close()
            await browser.close()

        self.assertEqual(len(tweets), 3)
        self.assertEqual(tweets[0].tweet_id, "1001")
        self.assertEqual(tweets[0].likes, 540)

    async def test_extracts_tweets_from_iframe_embed(self):
        scraper = PlaywrightXScraper(headless=True, page_delay_range=(0, 0), scroll_delay_range=(0, 0), scrolls_per_page=0)
        creator = CreatorTarget(display_name="Naval Ravikant", username="naval", tier="core", enabled=True)
        embed_fixture = """
<!DOCTYPE html>
<html lang="en">
  <body>
    <iframe srcdoc='
      <!DOCTYPE html>
      <html lang="en">
        <body>
          <article data-testid="tweet">
            <a href="/naval/status/2001"><time datetime="2026-04-02T08:00:00Z"></time></a>
            <div data-testid="tweetText">Leverage turns time into an asset when the system keeps producing after your effort stops.</div>
          </article>
          <article data-testid="tweet">
            <a href="/naval/status/2002"><time datetime="2026-04-02T07:00:00Z"></time></a>
            <div data-testid="tweetText">Most people chase income. Smart people build assets that keep compounding after the sprint.</div>
          </article>
        </body>
      </html>'></iframe>
  </body>
</html>
"""

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(embed_fixture)
            tweets = await scraper._extract_tweets_from_embed(page, creator, limit=10)
            await context.close()
            await browser.close()

        self.assertEqual(len(tweets), 2)
        self.assertEqual(tweets[0].tweet_id, "2001")
        self.assertEqual(tweets[0].creator_tier, "core")


if __name__ == "__main__":
    unittest.main()

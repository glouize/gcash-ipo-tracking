"""
src/ingestion/sentiment.py
───────────────────────────
Aggregates sentiment signals for GCash IPO from:
  1. Reddit (r/phinvest, r/PHStockMarket) via PRAW
  2. Philippine financial news RSS feeds
  3. Google Trends (pytrends)

Sentiment is scored using VADER (–1.0 = very negative, +1.0 = very positive).
"""

import logging
import os
import time
from datetime import datetime, timedelta

import feedparser
import pandas as pd
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

# ── Search Keywords ───────────────────────────────────────────────────────────
SEARCH_TERMS = ["GCash IPO", "GCASH PSE", "Mynt IPO", "GCASH stock", "GCash listing"]

# ── RSS News Feeds ────────────────────────────────────────────────────────────
NEWS_FEEDS = {
    "BusinessWorld PH":     "https://www.bworldonline.com/feed/",
    "Philippine Star Biz":  "https://www.philstar.com/rss/business",
    "Manila Bulletin Mkts": "https://mb.com.ph/category/business/feed/",
    "Inquirer Business":    "https://business.inquirer.net/feed/",
    "ABS-CBN News":         "https://news.abs-cbn.com/rss/news",
    "Reuters Asia":         "https://feeds.reuters.com/reuters/asiaNews",
}


# ─────────────────────────────────────────────────────────────────────────────
# Reddit Sentiment
# ─────────────────────────────────────────────────────────────────────────────

def fetch_reddit_sentiment(days_back: int = 7) -> pd.DataFrame:
    """
    Fetch GCash-related Reddit posts from Philippine investing subreddits.
    Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env.

    Returns DataFrame with columns: date, subreddit, title, score, sentiment, compound.
    """
    client_id     = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent    = os.getenv("REDDIT_USER_AGENT", "gcash-ipo-tracker:v1.0")

    if not client_id or not client_secret:
        logger.warning(
            "Reddit credentials not found in .env — skipping Reddit sentiment.\n"
            "Register a free app at https://www.reddit.com/prefs/apps"
        )
        return pd.DataFrame()

    try:
        import praw
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        subreddits = ["phinvest", "PHStockMarket", "philippines"]
        rows = []
        cutoff = datetime.utcnow() - timedelta(days=days_back)

        for sub_name in subreddits:
            subreddit = reddit.subreddit(sub_name)
            for term in SEARCH_TERMS:
                try:
                    for post in subreddit.search(term, limit=50, sort="new"):
                        created = datetime.utcfromtimestamp(post.created_utc)
                        if created < cutoff:
                            continue
                        text = f"{post.title} {post.selftext[:200]}"
                        scores = analyzer.polarity_scores(text)
                        rows.append({
                            "date":       created.date(),
                            "subreddit":  sub_name,
                            "title":      post.title,
                            "upvotes":    post.score,
                            "comments":   post.num_comments,
                            "sentiment":  _label(scores["compound"]),
                            "compound":   scores["compound"],
                        })
                    time.sleep(0.5)  # Respect Reddit rate limits
                except Exception as e:
                    logger.warning("Reddit search error (%s / %s): %s", sub_name, term, e)

        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df.sort_values("date", ascending=False, inplace=True)
        return df

    except ImportError:
        logger.error("praw not installed. Run: pip install praw")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# RSS News Sentiment
# ─────────────────────────────────────────────────────────────────────────────

def fetch_news_sentiment(days_back: int = 14) -> pd.DataFrame:
    """
    Fetch and score news articles from Philippine financial RSS feeds.
    Filters only articles mentioning GCash/Mynt/GCASH.

    Returns DataFrame with columns: date, source, title, url, sentiment, compound.
    """
    rows = []
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    keywords = ["gcash", "mynt", "gcash ipo", "gcash pse"]

    for source, feed_url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")
                text    = f"{title} {summary}".lower()

                if not any(kw in text for kw in keywords):
                    continue

                # Parse publication date
                published = entry.get("published_parsed")
                if published:
                    pub_dt = datetime(*published[:6])
                    if pub_dt < cutoff:
                        continue
                else:
                    pub_dt = datetime.utcnow()

                scores = analyzer.polarity_scores(f"{title} {summary}")
                rows.append({
                    "date":      pub_dt.date(),
                    "source":    source,
                    "title":     title,
                    "url":       entry.get("link", ""),
                    "sentiment": _label(scores["compound"]),
                    "compound":  scores["compound"],
                })
        except Exception as e:
            logger.warning("RSS feed error (%s): %s", source, e)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", ascending=False, inplace=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Google Trends
# ─────────────────────────────────────────────────────────────────────────────

def fetch_google_trends(keyword: str = "GCash IPO", geo: str = "PH") -> pd.DataFrame:
    """
    Fetch Google Trends data for the GCash IPO search term in the Philippines.
    Returns a DataFrame with date and interest_score (0–100).
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=480)  # UTC+8 (Philippine Time)
        pt.build_payload([keyword], cat=0, timeframe="today 3-m", geo=geo)
        data = pt.interest_over_time()

        if data.empty:
            return pd.DataFrame()

        data = data.reset_index()[["date", keyword]].rename(
            columns={keyword: "interest_score"}
        )
        data["keyword"] = keyword
        return data

    except Exception as e:
        logger.warning("Google Trends fetch failed: %s", e)
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def build_daily_sentiment(days_back: int = 14) -> pd.DataFrame:
    """
    Aggregate Reddit + News sentiment into a daily sentiment score.
    Returns DataFrame: date, mention_count, avg_compound, dominant_sentiment.
    """
    reddit_df = fetch_reddit_sentiment(days_back)
    news_df   = fetch_news_sentiment(days_back)

    frames = []
    if not reddit_df.empty:
        frames.append(reddit_df[["date", "compound"]])
    if not news_df.empty:
        frames.append(news_df[["date", "compound"]])

    if not frames:
        logger.warning("No sentiment data available — returning empty DataFrame")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])

    daily = (
        combined.groupby("date")["compound"]
        .agg(mention_count="count", avg_compound="mean")
        .reset_index()
    )
    daily["dominant_sentiment"] = daily["avg_compound"].apply(_label)
    return daily.sort_values("date")


def _label(compound: float) -> str:
    """Convert VADER compound score to a human-readable label."""
    if compound >= 0.05:
        return "Bullish"
    elif compound <= -0.05:
        return "Bearish"
    return "Neutral"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\n=== News Sentiment ===")
    news = fetch_news_sentiment(days_back=14)
    if not news.empty:
        print(news[["date", "source", "title", "sentiment"]].head(10).to_string(index=False))
    else:
        print("No GCash articles found in RSS feeds (check feeds or broaden date range)")

    print("\n=== Google Trends: 'GCash IPO' in PH ===")
    trends = fetch_google_trends()
    if not trends.empty:
        print(trends.tail(10).to_string(index=False))
    else:
        print("Google Trends unavailable (rate-limited or no data)")

    print("\n=== Daily Sentiment Summary ===")
    daily = build_daily_sentiment()
    if not daily.empty:
        print(daily.tail(7).to_string(index=False))

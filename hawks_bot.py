import os
import requests
import discord
import feedparser
from discord.ext import tasks, commands
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")  # optional later

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

FEEDS = [
    "https://www.espn.com/espn/rss/nba/news",
    "https://www.cbssports.com/rss/headlines/nba/",
    "https://sports.yahoo.com/nba/rss/",
    "https://www.peachtreehoops.com/rss/current",
    "https://www.si.com/nba/hawks/rss",
]

KEYWORDS = [
    "hawks", "atlanta hawks", "atlanta",
    "trae young", "jalen johnson", "dyson daniels",
    "zaccharie risacher", "onyeka okongwu", "cj mccollum",
]

URGENT_KEYWORDS = [
    "trade", "traded", "signs", "signed", "waived",
    "injury", "injured", "out", "questionable", "doubtful",
    "surgery", "extension", "contract",
]

posted_links = set()
posted_games = set()


def get_hawks_news():
    normal_news = []
    urgent_news = []

    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            text = f"{title} {summary}".lower()

            if not link or link in posted_links:
                continue

            if any(keyword in text for keyword in KEYWORDS):
                item = {
                    "title": title,
                    "link": link,
                    "summary": summary[:250] or "Click to read the full story.",
                }

                if any(word in text for word in URGENT_KEYWORDS):
                    urgent_news.append(item)
                else:
                    normal_news.append(item)

                posted_links.add(link)

    return urgent_news[:5], normal_news[:5]


def get_hawks_games():
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    data = requests.get(url, timeout=10).json()

    games = []

    for event in data.get("events", []):
        competitors = event["competitions"][0]["competitors"]

        teams = [c["team"]["abbreviation"] for c in competitors]

        if "ATL" not in teams:
            continue

        game_id = event["id"]
        status = event["status"]["type"]["description"]
        short_status = event["status"]["type"]["shortDetail"]

        away = competitors[1]
        home = competitors[0]

        away_name = away["team"]["displayName"]
        home_name = home["team"]["displayName"]

        away_score = away.get("score", "0")
        home_score = home.get("score", "0")

        games.append({
            "id": game_id,
            "status": status,
            "short_status": short_status,
            "away": away_name,
            "home": home_name,
            "away_score": away_score,
            "home_score": home_score,
        })

    return games


async def send_news_embed(channel, item, urgent=False):
    embed = discord.Embed(
        title=item["title"],
        url=item["link"],
        description=item["summary"],
        color=discord.Color.red() if urgent else discord.Color.from_rgb(225, 68, 52),
    )

    embed.set_author(name="Atlanta Hawks News")
    embed.add_field(
        name="Type",
        value="🚨 Trade/Injury Alert" if urgent else "🏀 Daily Hawks News",
        inline=False,
    )
    embed.set_footer(text="Hawks Discord Bot")

    await channel.send(embed=embed)


async def send_game_embed(channel, game):
    embed = discord.Embed(
        title=f"{game['away']} vs {game['home']}",
        description=game["short_status"],
        color=discord.Color.from_rgb(225, 68, 52),
    )

    embed.add_field(
        name="Score",
        value=f"{game['away']}: {game['away_score']}\n{game['home']}: {game['home_score']}",
        inline=False,
    )

    embed.add_field(name="Status", value=game["status"], inline=False)
    embed.set_footer(text="Atlanta Hawks Game Tracker")

    await channel.send(embed=embed)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    channel = await bot.fetch_channel(CHANNEL_ID)
    await channel.send("✅ Hawks bot is online: news, trades/injuries, and game alerts enabled.")

    if not urgent_news_check.is_running():
        urgent_news_check.start()

    if not daily_news_check.is_running():
        daily_news_check.start()

    if not game_check.is_running():
        game_check.start()


@tasks.loop(minutes=15)
async def urgent_news_check():
    channel = await bot.fetch_channel(CHANNEL_ID)
    urgent_news, _ = get_hawks_news()

    for item in urgent_news:
        await send_news_embed(channel, item, urgent=True)


@tasks.loop(hours=24)
async def daily_news_check():
    channel = await bot.fetch_channel(CHANNEL_ID)
    _, normal_news = get_hawks_news()

    if not normal_news:
        return

    await channel.send("🏀 **Daily Atlanta Hawks News Roundup**")

    for item in normal_news:
        await send_news_embed(channel, item, urgent=False)


@tasks.loop(minutes=5)
async def game_check():
    channel = await bot.fetch_channel(CHANNEL_ID)
    games = get_hawks_games()

    for game in games:
        post_key = f"{game['id']}-{game['status']}-{game['away_score']}-{game['home_score']}"

        if post_key in posted_games:
            continue

        posted_games.add(post_key)

        if game["status"] in ["Scheduled", "In Progress", "Final"]:
            await send_game_embed(channel, game)


@bot.command()
async def hawks(ctx):
    urgent_news, normal_news = get_hawks_news()
    games = get_hawks_games()

    await ctx.send("🏀 **Latest Atlanta Hawks Update**")

    for game in games:
        await send_game_embed(ctx.channel, game)

    for item in urgent_news + normal_news:
        await send_news_embed(ctx.channel, item, urgent=item in urgent_news)

    if not games and not urgent_news and not normal_news:
        await ctx.send("No fresh Hawks updates found right now.")


bot.run(TOKEN)